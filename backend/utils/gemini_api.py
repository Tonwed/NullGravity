
import logging
from typing import Any
from utils.proxy import get_http_client

logger = logging.getLogger("gemini_api")


class CodeAssistError(Exception):
    """Structured exception for Code Assist API errors."""
    def __init__(self, method: str, status_code: int, response_text: str):
        self.method = method
        self.status_code = status_code
        self.response_text = response_text
        # Try to parse as JSON
        try:
            import json
            self.response_body = json.loads(response_text)
        except Exception:
            self.response_body = None
        super().__init__(f"{method} failed ({status_code}): {response_text}")

# Gemini CLI 使用的 production 端点
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"

# Antigravity 使用的 sandbox 端点 (参考 quota.rs)
SANDBOX_ENDPOINT = "https://daily-cloudcode-pa.sandbox.googleapis.com"


async def code_assist_post(
    access_token: str, method: str, body: dict, timeout: float = 30.0, account_id: str | None = None
) -> dict:
    """
    Call Code Assist API on the PRODUCTION endpoint (Gemini CLI).
    """
    url = f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}:{method}"
    
    async with get_http_client(timeout=timeout, account_id=account_id) as client:
        resp = await client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Goland/2024.1", 
            },
        )
    
    if resp.status_code != 200:
        logger.warning(f"[Gemini CLI] {method} failed ({resp.status_code}): {resp.text}")
        raise CodeAssistError(method, resp.status_code, resp.text)
        
    return resp.json()


async def sandbox_post(
    access_token: str, method: str, body: dict, timeout: float = 30.0, account_id: str | None = None
) -> dict:
    """
    Call Code Assist API on the SANDBOX endpoint (Antigravity).
    参考 Antigravity Manager quota.rs 的实现。
    """
    url = f"{SANDBOX_ENDPOINT}/{CODE_ASSIST_API_VERSION}:{method}"
    
    # DEBUG LOGGING (Changed to WARNING to ensure visibility)
    logger.warning(f"[Sandbox] POST {url} | Payload: {body}")

    async with get_http_client(timeout=timeout, account_id=account_id) as client:
        resp = await client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "antigravity/1.15.8 windows/x86_64",
            },
        )
    
    if resp.status_code != 200:
        logger.warning(f"[Antigravity] {method} failed ({resp.status_code}): {resp.text}")
        logger.warning(f"[Antigravity] Response Headers: {resp.headers}")
        raise CodeAssistError(method, resp.status_code, resp.text)
        
    return resp.json()


async def fetch_available_models_gemini(access_token: str, project_id: str | None = None, account_id: str | None = None) -> list[dict]:
    """
    Fetch available models via PRODUCTION endpoint (Gemini CLI).
    """
    payload = {}
    if project_id:
        payload["project"] = project_id
    
    try:
        res = await code_assist_post(access_token, "fetchAvailableModels", payload, account_id=account_id)
        return res.get("models", [])
    except Exception as e:
        error_str = str(e)
        if "403" in error_str:
            logger.info(f"[Gemini CLI] fetchAvailableModels denied (expected for free tier): {e}")
        else:
            logger.warning(f"[Gemini CLI] fetchAvailableModels failed: {e}")
        return []


async def fetch_available_models_antigravity(access_token: str, project_id: str | None = None, account_id: str | None = None) -> dict:
    """
    Fetch available models via SANDBOX endpoint (Antigravity).
    Returns raw models dict (containing quotaInfo per model).
    Implements retry logic for both 403 Forbidden and network exceptions.
    Fallback project ID: 'bamboo-precept-lgxtn'.
    """
    FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"
    current_project_id = project_id or FALLBACK_PROJECT_ID
    url = f"{SANDBOX_ENDPOINT}/{CODE_ASSIST_API_VERSION}:fetchAvailableModels"
    
    # Helper to log exceptions to DB so they show up in frontend logs
    async def _log_exception(error_msg: str):
        try:
            from services.logger import save_log
            import asyncio
            asyncio.create_task(save_log(
                method="POST",
                path=url,
                status_code=0, # 0 indicates network/client error
                duration_ms=0,
                client_ip="Backend",
                headers={},
                request_body=None,
                response_body=None,
                error_detail=error_msg,
                account_id=account_id
            ))
        except: pass

    async def _do_req(pid: str):
        payload = {"project": pid}
        # logger.warning(f"[Sandbox] POST {url} | Payload: {payload}") # Too verbose?
        
        async with get_http_client(timeout=30.0, account_id=account_id) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "antigravity/1.15.8 windows/x86_64",
                },
            )
        return resp

    # Intentional Retry / Fallback Flow
    # 1. Try original project_id (if different from fallback)
    # 2. If fail (403 or Exception), try fallback project_id
    
    attempts = []
    if current_project_id != FALLBACK_PROJECT_ID:
        attempts.append(current_project_id)
    attempts.append(FALLBACK_PROJECT_ID)
    
    for i, pid in enumerate(attempts):
        try:
            resp = await _do_req(pid)
            
            # If 403, and we have more attempts, continue to next
            if resp.status_code == 403 and i < len(attempts) - 1:
                logger.warning(f"[Antigravity] 403 Forbidden with project '{pid}'. Retrying with fallback...")
                continue
                
            if resp.status_code != 200:
                logger.warning(f"[Antigravity] fetchAvailableModels failed ({resp.status_code}): {resp.text}")
                # Log non-exception errors are handled by proxy hook usually, but explicit warning is good
                if i == len(attempts) - 1:
                    return {}
                continue
                
            data = resp.json()
            return data.get("models", {})

        except Exception as e:
            logger.warning(f"[Antigravity] fetchAvailableModels exception with project '{pid}': {e}")
            if i == len(attempts) - 1:
                # Last attempt failed with exception - log it to user view
                await _log_exception(f"Network Error: {str(e)}")
                return {}
            # Otherwise continue to next attempt
            continue

    return {}

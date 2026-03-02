
import logging
from typing import Any
from utils.proxy import get_http_client, get_chrome_client
from utils.fingerprint import get_fingerprint, get_antigravity_endpoint, CODE_ASSIST_ENDPOINT, CODE_ASSIST_API_VERSION

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
    access_token: str, method: str, body: dict, timeout: float = 30.0,
    account_id: str | None = None, is_gcp_tos: bool = False,
    project_id: str | None = None,
) -> dict:
    """
    Call Code Assist API on the Antigravity endpoint.
    Endpoint is selected based on is_gcp_tos flag:
      - True  → cloudcode-pa.googleapis.com (production)
      - False → daily-cloudcode-pa.googleapis.com
    
    Headers 模拟官方 Antigravity main.js 的 w() 方法 (L394325-394332):
      - Content-Type: application/json
      - User-Agent: antigravity/{ideVersion} {os}/{arch}
      - Authorization: Bearer {token}
    
    ⚠️ 不发送 x-goog-api-client 和 x-goog-request-params！
    这些 header 属于 language_server (Go gRPC) 流程，不是 main.js 流程。
    发送 x-goog-request-params 会触发 Google 后端的 GCP IAM 权限检查，
    导致非 GCP ToS token 收到 403 PERMISSION_DENIED。
    """
    endpoint = get_antigravity_endpoint(is_gcp_tos)
    url = f"{endpoint}/{CODE_ASSIST_API_VERSION}:{method}"

    # 官方 main.js 的 User-Agent: "antigravity/{ideVersion} {os}/{arch}"
    # 参见 main.js L394282-394288: this.t getter
    from utils.fingerprint import get_fingerprint
    fp = get_fingerprint()
    ua = f"antigravity/{fp.ide_version} {fp.os_name}/{fp.arch}"

    logger.info(f"[Antigravity] POST {url} | gcp_tos={is_gcp_tos} | UA={ua}")

    # 只发送官方 main.js w() 方法中显式包含的 headers
    headers = {
        "Content-Type": "application/json",
        "User-Agent": ua,
        "Authorization": f"Bearer {access_token}",
    }

    async with get_chrome_client(timeout=timeout, account_id=account_id) as client:
        resp = await client.post(
            url,
            json=body,
            headers=headers,
        )

    if resp.status_code != 200:
        logger.warning(f"[Antigravity] {method} failed ({resp.status_code}): {resp.text}")
        logger.warning(f"[Antigravity] Response Headers: {dict(resp.headers) if resp.headers else {}}")
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


async def fetch_available_models_antigravity(
    access_token: str, project_id: str | None = None,
    account_id: str | None = None, is_gcp_tos: bool = False,
) -> dict:
    """
    Fetch available models via Antigravity endpoint.
    Endpoint is selected based on is_gcp_tos flag.
    Returns raw models dict (containing quotaInfo per model).
    
    Headers 模拟官方 Antigravity main.js 的 w() 方法:
      - Content-Type: application/json
      - User-Agent: antigravity/{ideVersion} {os}/{arch}
      - Authorization: Bearer {token}
    
    ⚠️ 不发送 x-goog-api-client / x-goog-request-params。
    """
    from utils.fingerprint import get_fingerprint
    fp = get_fingerprint()
    current_project_id = project_id or ""
    endpoint = get_antigravity_endpoint(is_gcp_tos)
    url = f"{endpoint}/{CODE_ASSIST_API_VERSION}:fetchAvailableModels"
    
    # 官方 main.js User-Agent
    ua = f"antigravity/{fp.ide_version} {fp.os_name}/{fp.arch}"
    
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
        payload = {"project": pid} if pid else {}
        # 只发送 main.js w() 方法的 headers — 不发送 gRPC 特有的 headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": ua,
            "Authorization": f"Bearer {access_token}",
        }

        async with get_chrome_client(timeout=30.0, account_id=account_id) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=headers,
            )
        return resp

    try:
        resp = await _do_req(current_project_id)
        
        if resp.status_code != 200:
            logger.warning(f"[Antigravity] fetchAvailableModels failed ({resp.status_code}): {resp.text}")
            return {}
            
        data = resp.json()
        return data.get("models", {})

    except Exception as e:
        logger.warning(f"[Antigravity] fetchAvailableModels exception with project '{current_project_id}': {e}")
        # Log exception to user view
        await _log_exception(f"Network Error: {str(e)}")
        return {}

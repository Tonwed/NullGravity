"""Google OAuth 2.0 authentication routes.

Implements the Authorization Code flow with PKCE for desktop applications.
Flow:
  1. Frontend calls POST /start -> gets auth_url + session_id
  2. User opens auth_url in browser (manually copy or click)
  3. Google redirects to /callback on our local server
  4. Backend exchanges code for tokens, fetches user info
  5. Frontend polls GET /status/{session_id} to know when auth is done
"""

import hashlib
import secrets
import time
import logging
import os
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.connection import get_session
from models.account import Account
from models.credential import OAuthCredential
from utils.proxy import get_http_client
# Import specific items to avoid circular deps or ensure availability
from utils.gemini_api import (
    CODE_ASSIST_ENDPOINT,
    CODE_ASSIST_API_VERSION
)
from services.event import log_event

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google OAuth 2.0 Clients Configuration
# ---------------------------------------------------------------------------

import os

# 1. Antigravity Native Client (Official)
ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
ANTIGRAVITY_CLIENT_SECRET = "GOCSPX-" + "K58FWR486LdLJ1mLB8sXC4z6qDAf"

# 2. Gemini CLI Client (Legacy NullGravity default)
GEMINI_CLI_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
GEMINI_CLI_CLIENT_SECRET = "GOCSPX-" + "4uHgMPm-1o7Sk-geV6Cu5clXFsxl"

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cloud-platform",
]

# Client Types
CLIENT_TYPE_ANTIGRAVITY = "antigravity"
CLIENT_TYPE_GEMINI = "gemini_cli"

def get_client_config(client_type: str):
    if client_type == CLIENT_TYPE_ANTIGRAVITY:
        return ANTIGRAVITY_CLIENT_ID, ANTIGRAVITY_CLIENT_SECRET
    else:
        return GEMINI_CLI_CLIENT_ID, GEMINI_CLI_CLIENT_SECRET


# In-memory store for pending OAuth sessions.
_pending_sessions: dict[str, dict] = {}
# Completed auth results
_completed_results: dict[str, dict] = {}
# Session TTL in seconds
SESSION_TTL = 300


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Cleanup stale sessions
# ---------------------------------------------------------------------------

def _cleanup_stale():
    now = time.time()
    stale_keys = [k for k, v in _pending_sessions.items() if now - v.get("created_at", 0) > SESSION_TTL]
    for k in stale_keys:
        _pending_sessions.pop(k, None)

    stale_result_keys = [k for k, v in _completed_results.items() if now - v.get("completed_at", 0) > SESSION_TTL]
    for k in stale_result_keys:
        _completed_results.pop(k, None)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AuthStartResponse(BaseModel):
    session_id: str
    auth_url: str


class AuthStatusResponse(BaseModel):
    status: str
    email: str | None = None
    account_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/google/start", response_model=AuthStartResponse)
async def start_google_auth(request: Request, client_type: str = CLIENT_TYPE_ANTIGRAVITY):
    _cleanup_stale()
    client_id, _ = get_client_config(client_type)
    
    code_verifier = _generate_code_verifier()
    state = secrets.token_urlsafe(32)
    session_id = secrets.token_urlsafe(16)

    # Use fixed loopback IP
    host = "127.0.0.1:8046"
    scheme = "http"
    redirect_uri = f"{scheme}://{host}/api/auth/google/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",
        "state": state,
        "code_challenge": _generate_code_challenge(code_verifier),
        "code_challenge_method": "S256",
        "prompt": "consent",
    }
    auth_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    _pending_sessions[state] = {
        "session_id": session_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
        "client_type": client_type,
    }

    return AuthStartResponse(session_id=session_id, auth_url=auth_url)


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if error:
        return _callback_html("Auth Failed", f"Google Error: {error}", success=False)
    if not code or not state:
        return _callback_html("Auth Failed", "Missing params", success=False)

    pending = _pending_sessions.get(state)
    if not pending:
        return _callback_html("Auth Failed", "Session expired", success=False)

    session_id = pending["session_id"]
    code_verifier = pending["code_verifier"]
    redirect_uri = pending["redirect_uri"]
    client_type = pending.get("client_type", CLIENT_TYPE_GEMINI)

    client_id, client_secret = get_client_config(client_type)

    try:
        payload = {
            "client_id": client_id,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if client_secret:
            payload["client_secret"] = client_secret

        async with get_http_client(timeout=30.0) as client:
            token_res = await client.post(GOOGLE_TOKEN_ENDPOINT, data=payload)

        if token_res.status_code != 200:
            err = token_res.json().get("error_description", token_res.text)
            _completed_results[session_id] = {"status": "error", "error": err, "completed_at": time.time()}
            _pending_sessions.pop(state, None)
            return _callback_html("Auth Failed", f"Token Exchange Error: {err}", success=False)

        tokens = token_res.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")
        
        token_expires_at = None
        from datetime import datetime, timezone, timedelta
        if expires_in:
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        async with get_http_client(timeout=15.0) as client:
            user_res = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if user_res.status_code != 200:
            _completed_results[session_id] = {"status": "error", "error": "Failed to fetch user info", "completed_at": time.time()}
            _pending_sessions.pop(state, None)
            return _callback_html("Auth Failed", "Unable to get user info", success=False)

        user_info = user_res.json()
        email = user_info.get("email")
        if not email:
             return _callback_html("Auth Failed", "No email in user info", success=False)

        # Create or Update Account
        result = await session.execute(select(Account).where(Account.email == email))
        account = result.scalar_one_or_none()

        from utils.antigravity import generate_device_profile
        
        is_new = False
        if not account:
            is_new = True
            account = Account(
                email=email,
                display_name=user_info.get("name"),
                avatar_url=user_info.get("picture"),
                status="active",
                device_profile=generate_device_profile(),
            )
            session.add(account)
            await session.flush()
        else:
            account.display_name = user_info.get("name") or account.display_name
            account.avatar_url = user_info.get("picture") or account.avatar_url
            account.status = "active"
            if not account.device_profile:
                 account.device_profile = generate_device_profile()
        
        # Update OAuthCredential
        cred_result = await session.execute(
            select(OAuthCredential).where(
                OAuthCredential.account_id == account.id,
                OAuthCredential.client_type == client_type
            )
        )
        credential = cred_result.scalar_one_or_none()
        
        if not credential:
            credential = OAuthCredential(
                account_id=account.id,
                client_type=client_type
            )
            session.add(credential)
            
        credential.access_token = access_token
        if refresh_token:
            credential.refresh_token = refresh_token
        credential.token_expires_at = token_expires_at
        credential.token_scope = tokens.get("scope")
        # Mark as "just synced" so auto-refresh doesn't immediately re-sync this credential
        # (the setup flow will handle the actual data sync right after this)
        credential.last_sync_at = datetime.now(timezone.utc)
        
        # Keep legacy account fields updated for backward compatibility (using last login)
        account.access_token = access_token
        if refresh_token:
            account.refresh_token = refresh_token
        account.token_expires_at = token_expires_at

        await session.commit()
        await session.refresh(account)

        # Cache avatar in background
        if account.avatar_url:
            import asyncio
            from services.avatar_service import download_and_cache_avatar

            async def _cache_avatar():
                try:
                    success = await download_and_cache_avatar(account.id, account.avatar_url)
                    if success:
                        from database.connection import async_session as sf
                        async with sf() as s:
                            r = await s.execute(select(Account).where(Account.id == account.id))
                            a = r.scalar_one_or_none()
                            if a:
                                a.avatar_cached = True
                                await s.commit()
                except Exception as e:
                    logger.warning(f"Background avatar cache failed: {e}")

            asyncio.create_task(_cache_avatar())

        # Set completed result THEN remove pending (order matters for race condition)
        _completed_results[session_id] = {
            "status": "success",
            "email": email,
            "account_id": account.id,
            "client_type": client_type,
            "completed_at": time.time(),
        }
        _pending_sessions.pop(state, None)  # Now safe to remove

        # Log event
        if is_new:
            await log_event(session, "account.create", f"New account connected: {email}", account_id=account.id, level="success")
        else:
            await log_event(session, "account.update", f"Account re-connected: {email}", account_id=account.id, level="info")

        return _callback_html(
            "认证成功",
            f"已成功登录 Google 账号: {email}\n你可以关闭此页面并返回 NullGravity。",
            success=True,
        )

    except Exception as e:
        logger.error(f"Auth error: {e}")
        _completed_results[session_id] = {"status": "error", "error": str(e), "completed_at": time.time()}
        _pending_sessions.pop(state, None)
        return _callback_html("系统错误", str(e), success=False)


@router.get("/google/status/{session_id}", response_model=AuthStatusResponse)
async def check_auth_status(session_id: str, session: AsyncSession = Depends(get_session)):
    _cleanup_stale()
    result = _completed_results.get(session_id)
    if result:
        return AuthStatusResponse(
            status=result["status"],
            email=result.get("email"),
            account_id=result.get("account_id"),
            error=result.get("error"),
        )
    for pending in _pending_sessions.values():
        if pending.get("session_id") == session_id:
            return AuthStatusResponse(status="pending")

    # No DB fallback — rely solely on in-memory state to avoid race conditions
    # where the callback hasn't committed yet but the DB check returns a match.
    return AuthStatusResponse(status="pending")


# ---------------------------------------------------------------------------
# Userinfo Refresh
# ---------------------------------------------------------------------------

class UserinfoRefreshResponse(BaseModel):
    success: bool
    display_name: str | None = None
    avatar_url: str | None = None
    error: str | None = None


@router.post("/google/userinfo/{account_id}", response_model=UserinfoRefreshResponse)
async def refresh_userinfo(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Fetch fresh userinfo from Google and update account profile.
    
    This updates display_name, avatar_url, and re-caches the avatar.
    """
    result = await session.execute(
        select(Account).where(Account.id == account_id).options(selectinload(Account.credentials))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Find a valid access token from any credential
    access_token = None
    from datetime import datetime, timezone
    for cred in account.credentials:
        if cred.access_token and cred.token_expires_at:
            if cred.token_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                access_token = cred.access_token
                break
    
    if not access_token:
        # Try legacy token
        access_token = account.access_token

    if not access_token:
        return UserinfoRefreshResponse(success=False, error="No valid access token")

    try:
        async with get_http_client(timeout=15.0, account_id=account_id) as client:
            user_res = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if user_res.status_code != 200:
            return UserinfoRefreshResponse(success=False, error=f"Google API error: {user_res.status_code}")

        user_info = user_res.json()
        
        # Update account profile
        new_name = user_info.get("name")
        new_picture = user_info.get("picture")
        
        if new_name:
            account.display_name = new_name
        if new_picture:
            old_url = account.avatar_url
            account.avatar_url = new_picture
            
            # Re-cache avatar if URL changed or not yet cached
            if new_picture != old_url or not account.avatar_cached:
                from services.avatar_service import download_and_cache_avatar
                success = await download_and_cache_avatar(account_id, new_picture)
                account.avatar_cached = success

        await session.commit()
        
        return UserinfoRefreshResponse(
            success=True,
            display_name=account.display_name,
            avatar_url=account.avatar_url,
        )
    except Exception as e:
        logger.error(f"Userinfo refresh failed: {e}")
        return UserinfoRefreshResponse(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------

class TokenRefreshResponse(BaseModel):
    success: bool
    email: str | None = None
    expires_at: str | None = None
    error: str | None = None


@router.post("/google/refresh/{account_id}", response_model=TokenRefreshResponse)
async def refresh_account_token(account_id: str, session: AsyncSession = Depends(get_session)):
    """Refresh tokens for all credentials associated with the account."""
    # Note: We now refresh ALL credentials associated with the account
    
    result = await session.execute(
        select(Account).where(Account.id == account_id).options(selectinload(Account.credentials))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.credentials:
        # Fallback to legacy fields if no credentials (should not happen with new accounts)
        if not account.refresh_token:
             return TokenRefreshResponse(success=False, error="No credentials found.")
        # Try to migrate legacy to a Gemini CLI credential? 
        # For now, let's just create a credential if missing from legacy data
        # ... logic omitted for brevity, assuming credentials exist ...

    success_count = 0
    errors = []
    
    from datetime import datetime, timezone, timedelta

    for cred in account.credentials:
        if not cred.refresh_token:
            continue
            
        client_id, client_secret = get_client_config(cred.client_type)
        
        try:
            async with get_http_client(timeout=30.0, account_id=account_id) as client:
                token_response = await client.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": cred.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            
            if token_response.status_code != 200:
                err = token_response.json().get("error", "Unknown error")
                errors.append(f"{cred.client_type}: {err}")
                if err in ("invalid_grant", "unauthorized_client"):
                    cred.access_token = None
                    cred.token_expires_at = None
                continue

            tokens = token_response.json()
            cred.access_token = tokens.get("access_token")
            expires_in = tokens.get("expires_in")
            if expires_in:
                cred.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            
            # Update legacy fields if it's the most recently used one?
            # Or just keep legacy fields as backup
            if cred.client_type == CLIENT_TYPE_GEMINI: 
                 account.access_token = cred.access_token
                 account.token_expires_at = cred.token_expires_at

            success_count += 1

        except Exception as e:
            errors.append(f"{cred.client_type}: {str(e)}")

    if success_count > 0:
        await session.commit()
        return TokenRefreshResponse(success=True, email=account.email)
    else:
        return TokenRefreshResponse(success=False, error="; ".join(errors) or "No refreshable credentials")


# ---------------------------------------------------------------------------
# Token Verification
# ---------------------------------------------------------------------------

class TokenVerifyResponse(BaseModel):
    valid: bool
    email: str | None = None
    expires_in: int | None = None
    scopes: list[str] | None = None
    error: str | None = None

GOOGLE_TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"

@router.get("/google/verify/{account_id}", response_model=TokenVerifyResponse)
async def verify_account_token(
    account_id: str,
    auto_refresh: bool = True,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Account).where(Account.id == account_id).options(selectinload(Account.credentials))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Find a valid token from any credential
    valid_token = None
    from datetime import datetime, timezone
    
    # 1. Check existing tokens for validity
    for cred in account.credentials:
        if cred.access_token and cred.token_expires_at:
            # Check expiry with buffer
            if cred.token_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                valid_token = cred.access_token
                break
    
    # 2. If no valid token, try refresh
    if not valid_token and auto_refresh:
        refresh_res = await refresh_account_token(account_id, session)
        if refresh_res.success:
            # Re-fetch to get new tokens
            await session.refresh(account)
            for cred in account.credentials:
                if cred.access_token:
                    valid_token = cred.access_token
                    break

    if not valid_token:
         # Fallback to legacy
         valid_token = account.access_token

    if not valid_token:
        return TokenVerifyResponse(valid=False, error="No valid token available")

    # Verify with Google
    try:
        async with get_http_client(timeout=10.0, account_id=account_id) as client:
            info_response = await client.get(
                GOOGLE_TOKENINFO_ENDPOINT,
                params={"access_token": valid_token},
            )

        if info_response.status_code != 200:
            return TokenVerifyResponse(valid=False, error="Token revoked or invalid")

        info = info_response.json()
        return TokenVerifyResponse(
            valid=True,
            email=info.get("email"),
            expires_in=int(info.get("expires_in", 0)),
            scopes=info.get("scope", "").split(" ") if info.get("scope") else None,
        )
    except Exception as e:
        return TokenVerifyResponse(valid=False, error=str(e))


def _callback_html(title: str, message: str, success: bool) -> HTMLResponse:
    color = "#10b981" if success else "#ef4444"
    icon = "✓" if success else "✕"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NullGravity - {title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh;
            background: #0a0a0a; color: #fafafa;
        }}
        .card {{
            text-align: center; padding: 48px;
            background: #171717; border-radius: 16px;
            border: 1px solid #262626;
            max-width: 420px; width: 90%;
        }}
        .icon {{
            width: 64px; height: 64px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 28px; margin: 0 auto 24px;
            background: {color}20; color: {color};
        }}
        h1 {{ font-size: 20px; margin-bottom: 12px; font-weight: 600; }}
        p {{ font-size: 14px; color: #a3a3a3; line-height: 1.6; white-space: pre-line; }}
        .close-hint {{
            margin-top: 24px; font-size: 12px; color: #525252;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon}</div>
        <h1>{title}</h1>
        <p>{message}</p>
        <p class="close-hint">此页面可以安全关闭</p>
    </div>
</body>
</html>""")


# ---------------------------------------------------------------------------
# Code Assist Setup
# ---------------------------------------------------------------------------

class CodeAssistSetupResponse(BaseModel):
    success: bool
    current_tier: str | None = None
    tier_name: str | None = None
    allowed_tiers: list[dict] | None = None
    ineligible_tiers: list[dict] | None = None
    project_id: str | None = None
    quota_buckets: list[dict] | None = None
    experiment_ids: list[int] | None = None
    experiment_flags: list[dict] | None = None
    error: str | None = None
    raw_responses: dict | None = None


@router.post("/google/setup/{account_id}", response_model=CodeAssistSetupResponse)
async def setup_code_assist(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Run post-login setup using unified sync service."""
    from services.sync import sync_account_info
    
    result = await session.execute(
        select(Account).where(Account.id == account_id).options(selectinload(Account.credentials))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Delegate to sync logic
    sync_result = await sync_account_info(session, account_id)
    
    if sync_result.get("success"):
        await log_event(session, "account.sync", "Account data synced manually", account_id=account_id, level="info")

    if not sync_result.get("success"):
        return CodeAssistSetupResponse(
            success=False,
            error=sync_result.get("error", "Sync failed"),
        )

    sync_results = sync_result.get("sync_results", {})
    gemini_res = sync_results.get("gemini_cli", {})
    
    # Just return whatever we have; frontend can deal with details
    return CodeAssistSetupResponse(
        success=True,
        current_tier=account.tier,
        tier_name=account.tier,
        project_id=gemini_res.get("project_id"), # Prefer Gemini CLI's project ID if available
        ineligible_tiers=account.ineligible_tiers,
        raw_responses=sync_results,
    )

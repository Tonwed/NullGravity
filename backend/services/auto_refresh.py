"""
Auto-refresh scheduler for account tokens.

Runs as a background asyncio task during application lifespan.
Refreshes each account's token at a configurable interval,
staggering requests by 3 seconds between accounts to avoid rate limits.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database.connection import async_session
from models.account import Account
from models.settings import AppSettings

logger = logging.getLogger("auto_refresh")

# Fixed stagger delay between accounts (seconds)
STAGGER_DELAY = 3

# Default refresh interval in minutes
DEFAULT_INTERVAL = 15


async def _get_setting(key: str, default: str) -> str:
    """Read a single setting from DB, return default if missing."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(AppSettings).where(AppSettings.key == key)
            )
            setting = result.scalar_one_or_none()
            return setting.value if setting else default
    except Exception:
        return default


async def _refresh_credential(cred_id: str, client_type: str) -> dict:
    """Refresh a single OAuthCredential token."""
    try:
        from models.credential import OAuthCredential
        from sqlalchemy.orm import selectinload

        async with async_session() as session:
            result = await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.id == cred_id)
                .options(selectinload(OAuthCredential.account))
            )
            cred = result.scalar_one_or_none()
            if not cred or not cred.refresh_token:
                return {"success": False, "error": "No refresh token"}

            # Get config
            from routers.auth import get_client_config, GOOGLE_TOKEN_ENDPOINT
            from utils.proxy import get_http_client
            from datetime import timedelta

            client_id, client_secret = get_client_config(client_type)
            
            payload = {
                "client_id": client_id,
                "refresh_token": cred.refresh_token,
                "grant_type": "refresh_token",
            }
            if client_secret:
                payload["client_secret"] = client_secret

            async with get_http_client(timeout=30.0, account_id=cred.account_id) as client:
                token_res = await client.post(GOOGLE_TOKEN_ENDPOINT, data=payload)

            if token_res.status_code != 200:
                err = token_res.json().get("error_description", "Unknown error")
                err_code = token_res.json().get("error", "")
                
                # If invalid grant, clear token
                if err_code in ("invalid_grant", "unauthorized_client"):
                    cred.access_token = None
                    cred.token_expires_at = None
                    await session.commit()
                return {"success": False, "error": f"{err_code}: {err}"}

            tokens = token_res.json()
            new_access_token = tokens.get("access_token")
            expires_in = tokens.get("expires_in")
            
            token_expires_at = None
            if expires_in:
                token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

            cred.access_token = new_access_token
            cred.token_expires_at = token_expires_at
            cred.updated_at = datetime.now(timezone.utc)
            cred.last_sync_at = datetime.now(timezone.utc)
            
            # Also update Account's last_sync_at
            if cred.account:
                cred.account.last_sync_at = datetime.now(timezone.utc)
            
            await session.commit()
            return {"success": True, "expires_at": str(token_expires_at)}

    except Exception as e:
        logger.error(f"Refresh failed for cred {cred_id}: {e}")
        return {"success": False, "error": str(e)}


async def _sync_account_info(account_id: str) -> dict:
    """Sync account info for all credentials (Gemini CLI first, then Antigravity)."""
    try:
        from services.sync import sync_account_info
        from services.event import log_event

        async with async_session() as session:
            # sync_account_info 会自动遍历所有 credentials 并分别同步
            result = await sync_account_info(session, account_id)
            
            if result.get("success"):
                await log_event(
                    session, 
                    "account.sync", 
                    "Account data updated automatically", 
                    account_id=account_id, 
                    level="info"
                )
            
            return result

    except Exception as e:
        logger.error(f"Sync failed for {account_id}: {e}")
        return {"success": False, "error": str(e)}


def _log_refresh_result(target: str, success: bool, detail: str) -> None:
    """Log a refresh attempt result."""
    if success:
        logger.info(f"✓ {target}: {detail}")
    else:
        logger.warning(f"✗ {target}: {detail}")


async def start_auto_refresh_scheduler() -> None:
    logger.info("Auto-refresh scheduler started")
    await asyncio.sleep(5)

    while True:
        try:
            # Check global refresh toggle
            enabled = await _get_setting("auto_refresh_enabled", "false")
            if enabled != "true":
                await asyncio.sleep(30)
                continue

            # Check client-specific toggles (default True if global is True)
            refresh_gemini = await _get_setting("auto_refresh_gemini_enabled", "true") == "true"
            refresh_antigravity = await _get_setting("auto_refresh_antigravity_enabled", "true") == "true"
            
            interval = int(await _get_setting("auto_refresh_interval", str(DEFAULT_INTERVAL)))
            if interval < 1: interval = DEFAULT_INTERVAL

            # Fetch credentials to refresh
            from models.credential import OAuthCredential
            async with async_session() as session:
                stmt = select(OAuthCredential).join(Account).where(Account.is_disabled == False)
                result = await session.execute(stmt)
                all_creds = result.scalars().all()

            if all_creds:
                logger.info(f"Auto-refresh: checking {len(all_creds)} credentials")
                
                now = datetime.now(timezone.utc)
                interval_seconds = interval * 60

                # Group credentials by account_id so we can refresh ALL tokens
                # for an account before syncing its data.
                from collections import defaultdict
                account_creds: dict[str, list] = defaultdict(list)
                for cred in all_creds:
                    account_creds[cred.account_id].append(cred)

                first_account = True
                for account_id, creds in account_creds.items():
                    # Phase 1: Refresh all credentials for this account
                    any_refreshed = False
                    for cred in creds:
                        # Check if allowed by client setting
                        if cred.client_type == "gemini_cli" and not refresh_gemini:
                            continue
                        if cred.client_type == "antigravity" and not refresh_antigravity:
                            continue

                        # Skip if recently synced (within the refresh interval)
                        if cred.last_sync_at:
                            sync_time = cred.last_sync_at
                            if sync_time.tzinfo is None:
                                sync_time = sync_time.replace(tzinfo=timezone.utc)
                            elapsed = (now - sync_time).total_seconds()
                            if elapsed < interval_seconds:
                                remaining = int(interval_seconds - elapsed)
                                logger.info(
                                    f"⏭ {cred.client_type}:{account_id[:8]} "
                                    f"skipped (synced {int(elapsed)}s ago, next in {remaining}s)"
                                )
                                continue

                        if not first_account or any_refreshed:
                            await asyncio.sleep(STAGGER_DELAY)

                        res = await _refresh_credential(cred.id, cred.client_type)
                        _log_refresh_result(
                            f"{cred.client_type}:{account_id[:8]}",
                            res["success"],
                            res.get("error") or "Refreshed"
                        )

                        if res["success"]:
                            any_refreshed = True

                    # Phase 2: Sync account data AFTER all tokens are refreshed
                    if any_refreshed:
                        await _sync_account_info(account_id)

                    first_account = False

            # Poll every 60s; actual refresh timing is controlled by per-credential
            # last_sync_at check above, so we don't need to sleep the full interval.
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(60)

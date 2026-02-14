
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.account import Account
from models.credential import OAuthCredential
from utils.gemini_api import (
    code_assist_post,
    sandbox_post,
    fetch_available_models_gemini,
    fetch_available_models_antigravity,
    CodeAssistError,
)
from utils.websocket import manager

logger = logging.getLogger("sync")

CLIENT_TYPE_GEMINI = "gemini_cli"
CLIENT_TYPE_ANTIGRAVITY = "antigravity"


async def _onboard_user(access_token: str, load_res: dict, client_metadata: dict, account_id: str | None = None) -> str | None:
    """
    Onboard a new user who has never used Gemini CLI before.
    Mirrors the logic in Gemini CLI setup.ts:
      1. Find the default tier from allowedTiers
      2. Call onboardUser with tierId + metadata
      3. Poll getOperation until done
      4. Extract cloudaicompanionProject.id from response
    
    Returns the project_id or None if onboarding failed.
    """
    import asyncio
    
    # Find default tier from allowedTiers
    allowed_tiers = load_res.get("allowedTiers") or []
    default_tier = None
    for tier in allowed_tiers:
        if tier.get("isDefault"):
            default_tier = tier
            break
    
    if not default_tier:
        logger.warning("[Gemini CLI] No default tier found in allowedTiers, cannot onboard")
        return None
    
    tier_id = default_tier.get("id")
    logger.info(f"[Gemini CLI] Onboarding user with tier: {tier_id} ({default_tier.get('name')})")
    
    # Build onboardUser request
    # For free tier: do NOT send cloudaicompanionProject (causes Precondition Failed)
    # For standard tier: also no project since we don't have one yet
    onboard_req = {
        "tierId": tier_id,
        "metadata": client_metadata,
    }
    
    try:
        # Step 1: Call onboardUser (Long Running Operation)
        lro_res = await code_assist_post(
            access_token, "onboardUser", onboard_req, timeout=60.0, account_id=account_id
        )
        logger.info(f"[Gemini CLI] onboardUser response: done={lro_res.get('done')}, name={lro_res.get('name')}")
        
        # Step 2: Poll getOperation until done
        operation_name = lro_res.get("name")
        if not lro_res.get("done") and operation_name:
            max_polls = 12  # 60 seconds max
            for i in range(max_polls):
                await asyncio.sleep(5)
                logger.info(f"[Gemini CLI] Polling operation {operation_name} (attempt {i+1}/{max_polls})")
                
                # getOperation is a GET request, need to handle specially
                from utils.proxy import get_http_client
                url = f"https://cloudcode-pa.googleapis.com/v1internal/{operation_name}"
                async with get_http_client(timeout=30.0, account_id=account_id) as client:
                    resp = await client.get(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {access_token}",
                            "User-Agent": "Goland/2024.1",
                        },
                    )
                
                if resp.status_code != 200:
                    logger.warning(f"[Gemini CLI] getOperation failed ({resp.status_code}): {resp.text}")
                    break
                    
                lro_res = resp.json()
                if lro_res.get("done"):
                    logger.info(f"[Gemini CLI] Operation completed")
                    break
            else:
                logger.warning("[Gemini CLI] onboardUser operation timed out after polling")
        
        # Step 3: Extract project_id from response
        response_data = lro_res.get("response", {})
        project_info = response_data.get("cloudaicompanionProject", {})
        project_id = project_info.get("id")
        
        if project_id:
            logger.info(f"[Gemini CLI] Onboarded successfully, project_id: {project_id}")
            return project_id
        else:
            logger.warning(f"[Gemini CLI] Onboard completed but no project_id in response: {lro_res}")
            return None
            
    except Exception as e:
        logger.error(f"[Gemini CLI] onboardUser failed: {e}")
        return None



def _extract_validation_from_body(response_body: dict | None) -> dict | None:
    """Extract validation URL from a parsed API error response body."""
    if not response_body or not isinstance(response_body, dict):
        return None
    
    try:
        error_obj = response_body.get("error", {})
        details = error_obj.get("details", [])
        
        for detail in details:
            # Check metadata (snake_case keys)
            metadata = detail.get("metadata", {})
            if "validation_url" in metadata:
                return {
                    "validation_url": metadata["validation_url"],
                    "message": metadata.get("validation_error_message", "Account verification required")
                }
            
            # Check links
            links = detail.get("links", [])
            for link in links:
                if link.get("description") == "Verify your account" and link.get("url"):
                    return {
                        "validation_url": link["url"],
                        "message": "Verify your account"
                    }
    except Exception:
        pass
    
    return None

async def _sync_gemini_cli(credential: OAuthCredential, session: AsyncSession) -> dict:
    """
    同步 Gemini CLI 客户端数据 (使用 production 端点)。
    Follows the same flow as Gemini CLI's setup.ts:
      1. loadCodeAssist → check status
      2. If no currentTier → onboardUser (new account)
      3. retrieveUserQuota → get models + quota
    """
    access_token = credential.access_token
    if not access_token:
        return {"success": False, "error": "No access token"}

    client_metadata = {
        "ideType": "GEMINI_CLI",
        "platform": "WINDOWS_AMD64",
        "pluginType": "GEMINI",
    }

    try:
        # Step 1: loadCodeAssist (production)
        load_res = await code_assist_post(
            access_token, "loadCodeAssist", {"metadata": client_metadata}, account_id=credential.account_id
        )

        # Extract tier
        tier_obj = load_res.get("paidTier") or load_res.get("currentTier") or {}
        tier_id = tier_obj.get("id")
        
        # Step 2: Check if user needs onboarding
        # If no currentTier AND no cloudaicompanionProject, user has never used Gemini CLI → onboard
        current_tier = load_res.get("currentTier")
        extracted_project = load_res.get("cloudaicompanionProject")
        
        if not current_tier and not extracted_project:
            logger.info(f"[Gemini CLI] Account not onboarded (no currentTier, no project). Initiating onboard...")
            onboard_project = await _onboard_user(
                access_token, load_res, client_metadata, account_id=credential.account_id
            )
            if onboard_project:
                extracted_project = onboard_project
                # Re-load to get updated tier info after onboarding
                try:
                    load_res = await code_assist_post(
                        access_token, "loadCodeAssist", {"metadata": client_metadata}, account_id=credential.account_id
                    )
                    tier_obj = load_res.get("paidTier") or load_res.get("currentTier") or {}
                    tier_id = tier_obj.get("id")
                    extracted_project = load_res.get("cloudaicompanionProject") or extracted_project
                    logger.info(f"[Gemini CLI] Post-onboard loadCodeAssist: tier={tier_id}, project={extracted_project}")
                except Exception as e:
                    logger.warning(f"[Gemini CLI] Post-onboard loadCodeAssist failed: {e}")
        
        # Set project_id
        if extracted_project:
            project_id = extracted_project
            credential.project_id = project_id
            logger.info(f"[Gemini CLI] project_id: {project_id}")
        else:
            # Fallback to existing cached value
            project_id = credential.project_id 
            if project_id:
                logger.warning(f"[Gemini CLI] loadCodeAssist missing project_id, using cached: {project_id}")
            else:
                logger.warning(f"[Gemini CLI] No project_id available. loadCodeAssist response keys: {list(load_res.keys())}")

        credential.tier = tier_id

        # Step 3: retrieveUserQuota (production) - Primary source for free tier models
        quota_data = []
        models_list = []
        validation_required = False
        
        if project_id:
            try:
                quota_res = await code_assist_post(
                    access_token, "retrieveUserQuota", {"project": project_id}, account_id=credential.account_id
                )
                quota_data = quota_res.get("buckets", [])
                
                # Populate models list from quota buckets
                for bucket in quota_data:
                    model_id = bucket.get("modelId")
                    if model_id:
                        model_entry = {
                            "name": model_id,
                            "remainingFraction": bucket.get("remainingFraction"),
                            "resetTime": bucket.get("resetTime")
                        }
                        models_list.append(model_entry)
                        
            except CodeAssistError as e:
                if e.status_code == 403 and e.response_body:
                    details = _extract_validation_from_body(e.response_body)
                    if details:
                        logger.warning(f"[Gemini CLI] Validation required, extracted URL: {details.get('validation_url', 'N/A')[:80]}")
                        validation_required = details
                    else:
                        logger.warning(f"[Gemini CLI] retrieveUserQuota 403 but no validation details found")
                        validation_required = True
                else:
                    logger.warning(f"[Gemini CLI] retrieveUserQuota failed: {e}")
            except Exception as e:
                logger.warning(f"[Gemini CLI] retrieveUserQuota failed: {e}")
        
        credential.models = models_list
        credential.quota_data = quota_data
        credential.last_sync_at = datetime.now(timezone.utc)

        return {
            "success": True,
            "client_type": CLIENT_TYPE_GEMINI,
            "tier": tier_id,
            "project_id": project_id,
            "models_count": len(credential.models),
            "quota_count": len(quota_data),
            "ineligible_tiers": load_res.get("ineligibleTiers", []),
            "validation_required": validation_required,
        }
    
    except CodeAssistError as e:
        logger.error(f"[Gemini CLI] Sync failed: {e}")
        details = _extract_validation_from_body(e.response_body) if e.response_body else None
        return {"success": False, "error": str(e), "validation_required": details or ("VALIDATION_REQUIRED" in str(e))}
    except Exception as e:
        logger.error(f"[Gemini CLI] Sync failed: {e}")
        return {"success": False, "error": str(e)}


async def _sync_antigravity(credential: OAuthCredential, session: AsyncSession) -> dict:
    """
    同步 Antigravity 客户端数据 (使用 sandbox 端点)。
    参考 Antigravity Manager quota.rs 的实现。
    """
    access_token = credential.access_token
    if not access_token:
        return {"success": False, "error": "No access token"}

    try:
        # Step 1: loadCodeAssist (sandbox) — 获取 project_id 和 tier
        load_res = await sandbox_post(
            access_token, "loadCodeAssist",
            {"metadata": {"ideType": "ANTIGRAVITY"}},
            account_id=credential.account_id
        )
        logger.warning(f"[Sync-Antigravity] loadCodeAssist result: {load_res}")

        tier_obj = load_res.get("paidTier") or load_res.get("currentTier") or {}
        tier_id = tier_obj.get("id")
        project_id = load_res.get("cloudaicompanionProject")
        logger.warning(f"[Sync-Antigravity] Extracted project_id: {project_id}")

        credential.tier = tier_id
        credential.project_id = project_id

        # Step 2: fetchAvailableModels (sandbox) — 同时包含模型列表和配额
        # Antigravity 的 fetchAvailableModels 返回 HashMap<String, ModelInfo>
        # 其中 ModelInfo 包含 quotaInfo { remainingFraction, resetTime }
        models_raw = await fetch_available_models_antigravity(
            access_token, project_id, account_id=credential.account_id
        )

        # 转换为 list[dict] 格式存储
        models_list = []
        if isinstance(models_raw, dict):
            for name, info in models_raw.items():
                model_entry = {"name": name}
                quota_info = info.get("quotaInfo") if isinstance(info, dict) else None
                if quota_info and isinstance(quota_info, dict):
                    # If remainingFraction is missing, quota is exhausted → 0
                    model_entry["remainingFraction"] = quota_info.get("remainingFraction", 0)
                    model_entry["resetTime"] = quota_info.get("resetTime")
                models_list.append(model_entry)

        credential.models = models_list
        credential.quota_data = models_list  # Antigravity 的 quota 就在 models 里
        credential.last_sync_at = datetime.now(timezone.utc)

        return {
            "success": True,
            "client_type": CLIENT_TYPE_ANTIGRAVITY,
            "tier": tier_id,
            "project_id": project_id,
            "models_count": len(models_list),
            "ineligible_tiers": load_res.get("ineligibleTiers", []),
        }

    except CodeAssistError as e:
        logger.error(f"[Antigravity] Sync failed: {e}")
        details = _extract_validation_from_body(e.response_body) if e.response_body else None
        return {"success": False, "error": str(e), "validation_required": details or ("VALIDATION_REQUIRED" in str(e))}
    except Exception as e:
        logger.error(f"[Antigravity] Sync failed: {e}")
        return {"success": False, "error": str(e)}


async def sync_account_info(
    session: AsyncSession,
    account_id: str,
    access_token: str | None = None
) -> dict:
    """
    同步账号信息：先刷新 Gemini CLI，再刷新 Antigravity。
    每个客户端数据分别存在各自的 OAuthCredential 记录上。
    Account 级别的 tier/quota 取最优值。
    
    NOTE: Uses its own fresh session internally to guarantee reading the latest
    committed data. The passed-in session parameter is kept for API compatibility
    but is NOT used.
    """
    # 1. 获取 Account + Credentials
    # ALWAYS use a FRESH session to ensure we see data committed by other sessions.
    # This is critical when adding Antigravity after Gemini CLI — the Antigravity
    # credential is committed by google_callback in a different request/session,
    # and the caller's session may have a stale transaction snapshot.
    from database.connection import async_session as session_factory
    
    async with session_factory() as sync_session:
        result = await sync_session.execute(
            select(Account)
            .where(Account.id == account_id)
            .options(selectinload(Account.credentials))
        )
        account = result.scalar_one_or_none()
    
        if not account:
            return {"success": False, "error": "Account not found"}

        try:
            await manager.broadcast({"type": "account_sync_start", "account_id": account_id})
        except Exception as e:
            logger.warning(f"Failed to broadcast start: {e}")

        # 2. 分类 credentials
        gemini_creds = [c for c in account.credentials if c.client_type == CLIENT_TYPE_GEMINI]
        antigravity_creds = [c for c in account.credentials if c.client_type == CLIENT_TYPE_ANTIGRAVITY]
        
        logger.info(
            f"[Sync] Account {account.email}: "
            f"total_creds={len(account.credentials)}, "
            f"gemini={len(gemini_creds)}, antigravity={len(antigravity_creds)}, "
            f"types={[c.client_type for c in account.credentials]}"
        )

        sync_results = {}

        # 3. 先同步 Gemini CLI
        for cred in gemini_creds:
            if cred.access_token:
                logger.info(f"[Sync] Syncing Gemini CLI for {account.email}")
                res = await _sync_gemini_cli(cred, sync_session)
                sync_results["gemini_cli"] = res

        # 4. 再同步 Antigravity
        for cred in antigravity_creds:
            if cred.access_token:
                logger.info(f"[Sync] Syncing Antigravity for {account.email}")
                res = await _sync_antigravity(cred, sync_session)
                sync_results["antigravity"] = res

        # 5. Account 级别汇总（取优先级最高的 tier）
        best_tier = None
        best_tier_name = None
        all_ineligible = []
        total_quota_percent = 100.0
        is_forbidden = False

        # Reset status — will be re-set below if issues are found
        account.status_reason = None
        account.status_details = None

        for cred in account.credentials:
            if cred.tier:
                # 优先 paid tier
                if not best_tier or cred.tier != "free-tier":
                    best_tier = cred.tier

        # 从 sync 结果中获取 ineligible_tiers
        gemini_result = sync_results.get("gemini_cli", {})
        antigravity_result = sync_results.get("antigravity", {})
        
        all_ineligible = []
        if gemini_result.get("success"):
            all_ineligible.extend(gemini_result.get("ineligible_tiers", []))
        if antigravity_result.get("success"):
            all_ineligible.extend(antigravity_result.get("ineligible_tiers", []))
            
        if all_ineligible:
            # Check forbidden
            critical_reasons = (
                "DASHER_USER", "INELIGIBLE_ACCOUNT", "RESTRICTED_NETWORK",
                "UNKNOWN_LOCATION", "UNSUPPORTED_LOCATION"
            )
            for tier in all_ineligible:
                reason = tier.get("reasonCode")
                
                # Check validation required (Actionable)
                if reason == "VALIDATION_REQUIRED":
                     account.status_reason = "VALIDATION_REQUIRED"
                     # Extract details
                     url = tier.get("validationUrl") or tier.get("validation_url")
                     msg = tier.get("validationErrorMessage") or tier.get("validation_error_message")
                     if url:
                         account.status_details = {"validation_url": url, "message": msg}
                
                if reason in critical_reasons:
                    # If this ineligibility applies to "free-tier" but we have a valid paid tier ("best_tier"), 
                    # we can likely ignore it (e.g. UNSUPPORTED_LOCATION might only restrict free access).
                    ineligible_tier_id = tier.get("tierId")
                    if best_tier and best_tier != "free-tier" and ineligible_tier_id == "free-tier":
                        # We have access to a better tier, so free-tier restriction doesn't block us entirely.
                        continue

                    is_forbidden = True
                    if account.status_reason != "VALIDATION_REQUIRED":
                        account.status_reason = reason
        
        # Check validation required from sync results (403 error path)
        gemini_val = gemini_result.get("validation_required")
        antigravity_val = antigravity_result.get("validation_required")
        
        if gemini_val or antigravity_val:
            account.status_reason = "VALIDATION_REQUIRED"
            # Extract details to persist URL
            val_details = gemini_val if isinstance(gemini_val, dict) else (antigravity_val if isinstance(antigravity_val, dict) else None)
            if val_details:
                account.status_details = val_details


        account.tier = best_tier
        account.is_forbidden = is_forbidden
        account.ineligible_tiers = all_ineligible if all_ineligible else None

        # Quota percent: Calculate from available credentials
        # Priority: Gemini CLI -> Antigravity
        target_quota_data = None
        
        if gemini_creds and gemini_creds[0].quota_data:
            target_quota_data = gemini_creds[0].quota_data
            account.quota_buckets = target_quota_data
        elif antigravity_creds and antigravity_creds[0].quota_data:
            # Fallback to Antigravity if Gemini CLI is not available
            target_quota_data = antigravity_creds[0].quota_data
            account.quota_buckets = target_quota_data

        if target_quota_data:
            min_fraction = 1.0
            has_fraction = False
            for bucket in target_quota_data:
                r_frac = bucket.get("remainingFraction")
                if r_frac is not None:
                    has_fraction = True
                    if r_frac < min_fraction:
                        min_fraction = r_frac
            if has_fraction:
                account.quota_percent = int((1.0 - min_fraction) * 100)

        # 合并所有客户端的 models 到 Account 级别
        all_models = []
        for cred in account.credentials:
            if cred.models:
                for m in cred.models:
                    if isinstance(m, dict):
                        m_copy = dict(m)
                        m_copy["_client_type"] = cred.client_type
                        all_models.append(m_copy)
        account.models = all_models if all_models else None

        # Label
        if best_tier:
            account.label = best_tier

        # Timestamps
        account.last_sync_at = datetime.now(timezone.utc)
        await sync_session.commit()

        try:
            await manager.broadcast({"type": "account_sync_end", "account_id": account_id, "success": True})
        except Exception as e:
            logger.warning(f"Failed to broadcast end: {e}")

        return {
            "success": True,
            "sync_results": sync_results,
            "account_tier": best_tier,
            "total_models": len(all_models),
        }


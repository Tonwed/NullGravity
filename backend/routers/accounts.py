"""Account management API routes."""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from models.account import Account
from schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountListResponse,
)
from services.avatar_service import get_avatar_path, has_cached_avatar
from services.event import log_event

router = APIRouter()

@router.get("/{account_id}/avatar")
async def get_account_avatar(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Serve cached avatar image for an account.
    
    Returns the locally cached avatar file if available.
    If not cached, redirects to the original Google URL and triggers
    background caching for next time.
    """
    # Serve from local cache if available
    if has_cached_avatar(account_id):
        avatar_path = get_avatar_path(account_id)
        return FileResponse(
            str(avatar_path),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",  # 24h browser cache
            },
        )

    # Fallback: get the Google URL and redirect
    result = await session.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.avatar_url:
        # Trigger background caching for next time
        import asyncio
        from services.avatar_service import download_and_cache_avatar

        async def _cache_bg():
            try:
                success = await download_and_cache_avatar(account_id, account.avatar_url)
                if success:
                    from database.connection import async_session as sf
                    async with sf() as s:
                        r = await s.execute(select(Account).where(Account.id == account_id))
                        a = r.scalar_one_or_none()
                        if a:
                            a.avatar_cached = True
                            await s.commit()
            except Exception:
                pass

        asyncio.create_task(_cache_bg())
        return RedirectResponse(url=account.avatar_url, status_code=302)

    raise HTTPException(status_code=404, detail="No avatar available")


@router.post("/{account_id}/launch")
async def launch_account(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Inject token and launch Antigravity with this account."""
    from utils.antigravity import (
        capture_snapshot, close_antigravity, inject_token,
        launch_antigravity, write_device_profile, generate_device_profile,
    )
    from models.settings import AppSettings
    from pathlib import Path as P
    import os

    # ── 0a. Read antigravity_path and antigravity_args from system settings ──
    settings_result = await session.execute(
        select(AppSettings).where(
            AppSettings.key.in_(["antigravity_path", "antigravity_args"])
        )
    )
    settings_map = {s.key: s.value for s in settings_result.scalars().all()}

    configured_exe = None
    path_val = settings_map.get("antigravity_path", "")
    if path_val and os.path.isfile(path_val):
        configured_exe = P(path_val)

    configured_args_str = settings_map.get("antigravity_args", "").strip()

    # ── 0b. Snapshot (while Antigravity is still alive) ─────────────────
    snap = capture_snapshot()

    # Override exe_path with configured path if available
    if configured_exe:
        snap.exe_path = configured_exe

    if not snap.db_path:
        raise HTTPException(
            status_code=500,
            detail="Antigravity database not found. Is it installed?",
        )

    # ── 1. Get account and Antigravity credential ───────────────────────
    from models.credential import OAuthCredential
    
    # Check if account exists
    acc_result = await session.execute(select(Account).where(Account.id == account_id))
    account = acc_result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Get Antigravity credential
    cred_result = await session.execute(
        select(OAuthCredential).where(
            OAuthCredential.account_id == account_id,
            OAuthCredential.client_type == "antigravity"
        )
    )
    cred = cred_result.scalar_one_or_none()

    if not cred or not cred.access_token:
        raise HTTPException(
            status_code=400,
            detail="该账号未连接 Antigravity 权限。请在账号管理中重新进行 Antigravity 授权。",
        )
    
    access_token = cred.access_token
    refresh_token = cred.refresh_token
    # expiry needs converting to timestamp int for injection
    import time
    expiry = int(cred.token_expires_at.timestamp()) if cred.token_expires_at else int(time.time() + 3600)

    # ── 2. Ensure device profile ────────────────────────────────────────
    if not account.device_profile:
        account.device_profile = generate_device_profile()
        await session.commit()
        await session.refresh(account)

    # ── 3. Close Antigravity (uses psutil, waits for exit) ──────────────
    close_antigravity()

    # ── 4. Write device profile (uses cached paths) ─────────────────────
    write_device_profile(
        account.device_profile,
        storage_path=snap.storage_path,
        db_path=snap.db_path,
    )

    # ── 5. Inject token (uses cached db path) ───────────────────────────
    # expiry is already calculated above from credential
    from datetime import timezone
    if cred.token_expires_at:
        dt = cred.token_expires_at
        if dt.tzinfo is None:
             dt = dt.replace(tzinfo=timezone.utc)
        expiry = int(dt.timestamp())
    else:
        import time
        expiry = int(time.time() + 3600)

    try:
        inject_token(
            snap.db_path,
            access_token,
            refresh_token or "",
            expiry,
            email=account.email
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to inject token: {str(e)}")

    # ── 6. Launch Antigravity (uses configured args > detected args) ───────
    # User-configured args take priority over auto-detected ones
    if configured_args_str:
        import shlex
        final_args = shlex.split(configured_args_str)
    else:
        final_args = snap.reusable_args

    launch_antigravity(exe_path=snap.exe_path, extra_args=final_args)

    await log_event(session, "app.launch", f"Launched Antigravity for {account.email}", account_id=account.id, level="info")

    return {"status": "success", "message": "Antigravity launched"}


@router.get("/{account_id}/device-profile")
async def get_device_profile(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the device fingerprint for an account."""
    from utils.antigravity import generate_device_profile

    result = await session.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Auto-generate if missing
    if not account.device_profile:
        account.device_profile = generate_device_profile()
        await session.commit()
        await session.refresh(account)

    return {"device_profile": account.device_profile}


@router.post("/{account_id}/device-profile/regenerate")
async def regenerate_device_profile(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Regenerate the device fingerprint for an account."""
    from utils.antigravity import generate_device_profile

    result = await session.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.device_profile = generate_device_profile()
    await session.commit()
    await session.refresh(account)

    return {"status": "success", "device_profile": account.device_profile}


@router.get("/", response_model=AccountListResponse)
async def list_accounts(
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List all accounts with optional search and pagination."""
    query = select(Account)
    count_query = select(func.count(Account.id))

    if search:
        query = query.where(Account.email.icontains(search))
        count_query = count_query.where(Account.email.icontains(search))

    # Total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated results
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    accounts = result.scalars().all()

    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=total,
    )


@router.post("/", response_model=AccountResponse, status_code=201)
async def create_account(
    data: AccountCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new account."""
    account = Account(
        email=data.email,
        provider=data.provider,
        label=data.label,
        refresh_token=data.refresh_token,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return AccountResponse.model_validate(account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a specific account by ID."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    data: AccountUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an account."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(account, key, value)

    await session.commit()
    await session.refresh(account)
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete an account."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    email = account.email
    await session.delete(account)
    await session.commit()
    
    await log_event(session, "account.delete", f"Account deleted: {email}", level="warning")


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------
from pydantic import BaseModel as _BaseModel
from models.credential import OAuthCredential
from sqlalchemy.orm import selectinload


class ExportRequest(_BaseModel):
    account_ids: list[str] = []


class _ExportCredential(_BaseModel):
    client_type: str
    refresh_token: str


class _ExportAccount(_BaseModel):
    email: str
    credentials: list[_ExportCredential]
    device_profile: dict | None = None


class ExportResponse(_BaseModel):
    accounts: list[_ExportAccount]


@router.post("/export", response_model=ExportResponse)
async def export_accounts(
    data: ExportRequest,
    session: AsyncSession = Depends(get_session),
):
    """Export accounts with refresh tokens for backup/migration."""
    query = select(Account).options(selectinload(Account.credentials))
    if data.account_ids:
        query = query.where(Account.id.in_(data.account_ids))
    result = await session.execute(query)
    accounts = result.scalars().all()

    export_list = []
    for acct in accounts:
        creds = []
        for c in acct.credentials:
            if c.refresh_token:
                creds.append(_ExportCredential(
                    client_type=c.client_type,
                    refresh_token=c.refresh_token,
                ))
        if creds:
            export_list.append(_ExportAccount(
                email=acct.email,
                credentials=creds,
                device_profile=acct.device_profile,
            ))
    return ExportResponse(accounts=export_list)


class _ImportCredential(_BaseModel):
    client_type: str = "gemini_cli"
    refresh_token: str


class _ImportAccount(_BaseModel):
    email: str | None = None
    refresh_token: str | None = None          # simple format compat
    credentials: list[_ImportCredential] = []  # full format
    device_profile: dict | None = None


class ImportRequest(_BaseModel):
    accounts: list[_ImportAccount]


class ImportResult(_BaseModel):
    success: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = []


@router.post("/import", response_model=ImportResult)
async def import_accounts(
    data: ImportRequest,
    session: AsyncSession = Depends(get_session),
):
    """Import accounts from JSON backup."""
    from utils.antigravity import generate_device_profile

    result = ImportResult()

    for item in data.accounts:
        # Normalize credentials: support simple {email, refresh_token} format
        creds = list(item.credentials)
        if not creds and item.refresh_token:
            creds.append(_ImportCredential(
                client_type="gemini_cli",
                refresh_token=item.refresh_token,
            ))
        if not creds:
            result.failed += 1
            result.errors.append(f"No credentials for {item.email or 'unknown'}")
            continue

        # Validate refresh tokens
        valid_creds = [c for c in creds if c.refresh_token and c.refresh_token.startswith("1//")]
        if not valid_creds:
            result.failed += 1
            result.errors.append(f"Invalid refresh token for {item.email or 'unknown'}")
            continue

        email = item.email or "imported@unknown"
        try:
            # Check for existing account
            existing = await session.execute(
                select(Account).options(selectinload(Account.credentials))
                .where(Account.email == email)
            )
            account = existing.scalar_one_or_none()

            if account:
                # Merge credentials
                existing_types = {c.client_type for c in account.credentials}
                added = False
                for vc in valid_creds:
                    if vc.client_type not in existing_types:
                        session.add(OAuthCredential(
                            account_id=account.id,
                            client_type=vc.client_type,
                            refresh_token=vc.refresh_token,
                        ))
                        added = True
                    else:
                        # Update refresh_token
                        for ec in account.credentials:
                            if ec.client_type == vc.client_type:
                                ec.refresh_token = vc.refresh_token
                                added = True
                if added:
                    result.success += 1
                else:
                    result.skipped += 1
            else:
                # Create new account
                account = Account(
                    email=email,
                    status="active",
                    device_profile=item.device_profile or generate_device_profile(),
                )
                session.add(account)
                await session.flush()

                for vc in valid_creds:
                    session.add(OAuthCredential(
                        account_id=account.id,
                        client_type=vc.client_type,
                        refresh_token=vc.refresh_token,
                    ))
                result.success += 1

            await session.commit()
        except Exception as e:
            result.failed += 1
            result.errors.append(f"{email}: {str(e)}")
            await session.rollback()

    return result


from utils.websocket import manager

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

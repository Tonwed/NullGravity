"""Settings management API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session, DATA_DIR
from models.settings import AppSettings
from schemas.settings import SettingUpdate, SettingsResponse
from utils.proxy import (
    set_cached_proxy,
    set_cached_proxy_enabled,
    get_proxy_status,
)
from services.antigravity_service import detect_antigravity_path, clear_antigravity_cache

router = APIRouter()

# Default settings
DEFAULT_SETTINGS = {
    "proxy_url": "",
    "proxy_enabled": "false",
    "language": "en",
    "theme": "dark",
    "data_dir": str(DATA_DIR),
    "auto_refresh_enabled": "false",
    "auto_refresh_interval": "15",
    "auto_refresh_gemini_enabled": "true",
    "auto_refresh_antigravity_enabled": "true",
    "antigravity_path": "",
    "antigravity_args": "",
}


@router.get("/", response_model=SettingsResponse)
async def get_all_settings(
    session: AsyncSession = Depends(get_session),
):
    """Get all settings, merging with defaults."""
    result = await session.execute(select(AppSettings))
    db_settings = {s.key: s.value for s in result.scalars().all()}

    # Merge: DB values override defaults
    merged = {**DEFAULT_SETTINGS, **db_settings}
    
    # Force data_dir to be the actual runtime path
    merged["data_dir"] = str(DATA_DIR)
    
    return SettingsResponse(settings=merged)


@router.put("/")
async def update_settings(
    updates: list[SettingUpdate],
    session: AsyncSession = Depends(get_session),
):
    """Update one or more settings."""
    for update in updates:
        result = await session.execute(
            select(AppSettings).where(AppSettings.key == update.key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = update.value
        else:
            setting = AppSettings(key=update.key, value=update.value)
            session.add(setting)

        # Side-effects: update proxy caches immediately
        if update.key == "proxy_url":
            set_cached_proxy(update.value if update.value else None)
        elif update.key == "proxy_enabled":
            set_cached_proxy_enabled(update.value == "true")

    await session.commit()
    return {"status": "ok"}


@router.get("/proxy/status")
async def proxy_status(force: bool = Query(False)):
    """Get the current proxy status (cached by default)."""
    return await get_proxy_status(force=force)


@router.get("/antigravity/detect")
async def detect_antigravity():
    """Detect Antigravity executable path."""
    path = detect_antigravity_path()
    return {"path": path}


@router.get("/antigravity/args")
async def detect_antigravity_args():
    """Detect launch arguments from a currently running Antigravity process.
    
    Reads the command line of running Antigravity processes and extracts
    reusable arguments like --user-data-dir, --extensions-dir, etc.
    
    Returns:
        - process_found: whether any Antigravity process was found
        - detected: whether reusable args were extracted
        - args: the extracted args string
    """
    import logging
    logger = logging.getLogger("antigravity")
    from utils.antigravity import find_antigravity_processes

    procs = find_antigravity_processes()
    if not procs:
        logger.info("No Antigravity processes found for args detection")
        return {"args": "", "detected": False, "process_found": False}

    logger.info(f"Found {len(procs)} Antigravity process(es), checking cmdline args")

    # Collect reusable args from the first matching process
    reusable: list[str] = []
    for p in procs:
        logger.debug(f"  PID {p.pid}: cmdline = {p.cmdline}")
        for i, arg in enumerate(p.cmdline):
            if arg in ("--user-data-dir", "--extensions-dir"):
                if i + 1 < len(p.cmdline):
                    reusable.extend([arg, p.cmdline[i + 1]])
            elif arg.startswith("--user-data-dir=") or arg.startswith("--extensions-dir="):
                reusable.append(arg)
        if reusable:
            break

    return {
        "args": " ".join(reusable),
        "detected": bool(reusable),
        "process_found": True,
    }


@router.post("/antigravity/clear-cache")
async def clear_cache():
    """Clear Antigravity cache."""
    return clear_antigravity_cache()


@router.post("/antigravity/browse")
async def browse_antigravity():
    """Open a native file dialog to select Antigravity executable.
    
    Runs the dialog in a separate thread to avoid blocking the event loop.
    """
    import asyncio
    import platform

    def _open_dialog() -> str | None:
        system = platform.system().lower()

        if system == "windows":
            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.update()
                path = filedialog.askopenfilename(
                    title="Select Antigravity Executable",
                    filetypes=[
                        ("Executable files", "*.exe"),
                        ("All files", "*.*"),
                    ],
                )
                root.destroy()
                return path if path else None
            except Exception:
                return None

        elif system == "darwin":
            try:
                import subprocess
                result = subprocess.run(
                    [
                        "osascript", "-e",
                        'tell application "System Events" to activate',
                        "-e",
                        'POSIX path of (choose file with prompt "Select Antigravity" of type {"app"})',
                    ],
                    capture_output=True, text=True, timeout=60,
                )
                path = result.stdout.strip()
                return path if path else None
            except Exception:
                return None

        else:  # Linux
            try:
                import subprocess
                result = subprocess.run(
                    ["zenity", "--file-selection", "--title=Select Antigravity"],
                    capture_output=True, text=True, timeout=60,
                )
                path = result.stdout.strip()
                return path if path else None
            except Exception:
                return None

    path = await asyncio.to_thread(_open_dialog)
    return {"path": path}


@router.post("/data-dir/open")
async def open_data_dir():
    """Open the data directory in the system file manager."""
    import platform
    import subprocess
    import os
    
    # Ensure directory exists
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    path = str(DATA_DIR)
    system = platform.system().lower()
    
    try:
        if system == "windows":
            os.startfile(path)
        elif system == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/storage/stats")
async def get_storage_stats(session: AsyncSession = Depends(get_session)):
    """Get storage usage statistics."""
    import os
    from sqlalchemy import func
    from models.log import Log
    from models.event import Event
    
    # 1. DB Row Counts
    logs_count = (await session.execute(select(func.count(Log.id)))).scalar() or 0
    events_count = (await session.execute(select(func.count(Event.id)))).scalar() or 0
    
    # 2. File Sizes
    def get_size(path):
        total = 0
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_size(entry.path)
        except FileNotFoundError:
            pass
        return total

    # Total Data Dir Size
    total_size = get_size(DATA_DIR)
    
    # Avatars Size
    avatars_dir = DATA_DIR / "avatars"
    avatars_size = get_size(avatars_dir)
    
    # DB File Size
    db_file = DATA_DIR / "nullgravity.db"
    db_size = db_file.stat().st_size if db_file.exists() else 0
    
    # Core Data (approximate as total valid data excluding avatars cache?)
    # User definition: Software Body (not here) + Account Core (DB) + etc.
    # We'll report:
    # - core_size: DB size (since config/creds are in DB).
    # - cache_size: Avatars + Logs (logical). 
    #   * Since logs are inside DB, identifying their physical size is hard.
    #   * We'll just report DB size as "Database" and Avatars as "Cache".
    #   * But for the UI "Core vs Cache", we can interpret:
    #     Core = DB Size (minus some arbitrary amount? No, just DB size).
    #     Cache = Avatars Size.
    #   * If user clears logs, DB size should shrink (VACUUM).
    
    return {
        "total_size": total_size,
        "db_size": db_size,
        "avatars_size": avatars_size,
        "logs_count": logs_count,
        "events_count": events_count,
        "data_dir": str(DATA_DIR)
    }


@router.post("/storage/clear")
async def clear_storage(
    type: str = Query(..., description="logs, events, avatars, all"),
    session: AsyncSession = Depends(get_session)
):
    """Clear specific storage items."""
    from sqlalchemy import delete, text
    from models.log import Log
    from models.event import Event
    import shutil
    
    try:
        if type in ["logs", "all_logs", "all"]:
            await session.execute(delete(Log))
            
        if type in ["events", "all_logs", "all"]:
            await session.execute(delete(Event))
            
        if type in ["avatars", "all"]:
            avatars_dir = DATA_DIR / "avatars"
            if avatars_dir.exists():
                # Delete all files in avatars dir
                for item in avatars_dir.iterdir():
                    if item.is_file():
                        item.unlink()
        
        await session.commit()
        
        # Run VACUUM if logs/events were cleared to reclaim DB space
        # VACUUM cannot run inside a transaction block in some drivers.
        # But here we committed. SQLite requires VACUUM to be outside transaction?
        # In aiosqlite, execute("VACUUM") works if autocommit is on.
        # With SQLAlchemy async session, it's safer to try:
        if type in ["logs", "events", "all_logs", "all"]:
            try:
                # We need to ensure we're not in a transaction.
                # session.commit() ended the transaction.
                # But begin() starts one implicitly?
                # Trying to run VACUUM via session.execute might fail.
                # Let's try raw connection if possible, or simple execute.
                # 'VACUUM' must be run outside of a transaction block
                # Setting isolation_level="AUTOCOMMIT" on engine might be needed.
                # For now, let's skip automatic VACUUM or try it and catch error.
                pass
                # await session.execute(text("VACUUM")) 
                # ^ This often fails in standard async session setup.
                # A workaround is to rely on user restarting or auto-vacuum if enabled.
                # Enabling auto_vacuum via PRAGMA might be better?
                # For now, we deleted the rows.
            except Exception as e:
                print(f"VACUUM failed: {e}")

        return {"status": "ok", "cleared": type}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

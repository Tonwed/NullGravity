
import os
import shutil
import platform
import logging
from pathlib import Path

logger = logging.getLogger("antigravity_service")

def get_system_platform():
    return platform.system().lower()

def detect_antigravity_path() -> str | None:
    """
    Detect Antigravity executable path based on standard installation locations.
    """
    system = get_system_platform()
    
    import psutil
    
    # Check running processes first (most reliable)
    try:
        current_pid = os.getpid()
        for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
            try:
                if proc.pid == current_pid:
                    continue
                    
                name = proc.info['name'].lower()
                exe = proc.info['exe']
                
                if not exe:
                    continue
                    
                exe_lower = exe.lower()
                
                # Check based on platform
                is_match = False
                if system == "windows":
                    if name == "antigravity.exe" or "antigravity.exe" in exe_lower:
                        is_match = True
                elif system == "darwin":
                    if "antigravity.app" in exe_lower and "helper" not in exe_lower:
                         # Try to find .app path
                         if ".app" in exe:
                             app_idx = exe.find(".app")
                             return exe[:app_idx+4]
                         return exe
                elif system == "linux":
                     if name == "antigravity" or "/antigravity" in exe_lower:
                         is_match = True
                         
                if is_match:
                    if system == "darwin":
                         # Already handled above for .app path
                         return exe
                    return exe
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except ImportError:
        logger.warning("psutil not installed, skipping process check")
    except Exception as e:
        logger.error(f"Error checking processes: {e}")

    if system == "windows":
        # Check standard Windows paths
        candidates = [
            # User installation (preferred)
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe"),
            # System installation
            os.path.expandvars(r"%PROGRAMFILES%\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity\Antigravity.exe"),
            # Google locations (legacy/alternative)
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Antigravity\Application\antigravity.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Antigravity\Application\antigravity.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Antigravity\Application\antigravity.exe"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

    elif system == "darwin": # macOS
        # Check /Applications
        candidates = [
            "/Applications/Antigravity.app",
            os.path.expanduser("~/Applications/Antigravity.app"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
                
    elif system == "linux":
        # Check common Linux paths
        candidates = [
            "/usr/bin/antigravity",
            "/opt/Antigravity/antigravity",
            "/usr/share/antigravity/antigravity",
            "/usr/local/bin/antigravity",
            os.path.expanduser("~/.local/bin/antigravity"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

    return None

def get_cache_paths() -> list[Path]:
    """Get list of Antigravity cache directories to clear."""
    system = get_system_platform()
    paths = []
    
    home = Path.home()

    if system == "darwin":
        paths.extend([
            home / "Library/HTTPStorages/com.google.antigravity",
            home / "Library/Caches/com.google.antigravity",
            home / ".antigravity",
            home / ".config/antigravity",
        ])
    elif system == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            local = Path(local_app_data)
            paths.extend([
                local / "Google" / "Antigravity",
                local / "Antigravity" / "Cache",
            ])
        
        app_data = os.environ.get("APPDATA")
        if app_data:
            roaming = Path(app_data)
            paths.extend([
                roaming / "Antigravity" / "Cache",
            ])
            
    elif system == "linux":
        paths.extend([
            home / ".cache/Antigravity",
            home / ".cache/google-antigravity",
            home / ".antigravity",
        ])
        
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            xdg = Path(xdg_cache)
            paths.extend([
                xdg / "Antigravity",
                xdg / "google-antigravity",
            ])
            
    return paths

def clear_antigravity_cache() -> dict:
    """
    Clear Antigravity cache directories.
    Returns details about cleared paths and errors.
    """
    paths = get_cache_paths()
    cleared = []
    errors = []
    freed_bytes = 0
    
    for path in paths:
        if not path.exists():
            continue
            
        try:
            # Calculate size for reporting
            size = 0
            if path.is_file():
                size = path.stat().st_size
            else:
                for p in path.rglob('*'):
                    if p.is_file():
                        size += p.stat().st_size
            
            # Remove
            if path.is_dir():
                shutil.rmtree(path)
            else:
                os.remove(path)
                
            cleared.append(str(path))
            freed_bytes += size
            logger.info(f"Cleared cache path: {path} ({size} bytes)")
            
        except Exception as e:
            error_msg = f"Failed to clear {path}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
            
    return {
        "success": len(errors) == 0,
        "cleared_paths": cleared,
        "errors": errors,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2)
    }

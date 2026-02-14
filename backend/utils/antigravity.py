
import os
import sys
import json
import sqlite3
import base64
import time
import uuid
import logging
import psutil
import subprocess
import secrets
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("antigravity")

# ---------------------------------------------------------------------------
# Protobuf Helpers (Complete Impl for Read/Write)
# ---------------------------------------------------------------------------

def encode_varint(value: int) -> bytes:
    buf = bytearray()
    while True:
        towrite = value & 0x7F
        value >>= 7
        if value:
            buf.append(towrite | 0x80)
        else:
            buf.append(towrite)
            break
    return bytes(buf)

def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Result: (value, new_offset)"""
    result = 0
    shift = 0
    pos = offset
    length = len(data)
    
    while True:
        if pos >= length:
             # Incomplete varint is hard to handle gracefully without more context,
             # but standard protobuf parsers throw error.
             raise ValueError("Incomplete varint")
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if not (byte & 0x80):
            return result, pos
        shift += 7

def encode_len_delim(field_num: int, data: bytes) -> bytes:
    tag = (field_num << 3) | 2
    return encode_varint(tag) + encode_varint(len(data)) + data

def encode_string(field_num: int, value: str) -> bytes:
    return encode_len_delim(field_num, value.encode('utf-8'))

# --- Reading/Editing Utilities ---

def skip_field(data: bytes, offset: int, wire_type: int) -> int:
    """Return new offset after skipping the field."""
    if wire_type == 0: # Varint
        _, new_pos = decode_varint(data, offset)
        return new_pos
    elif wire_type == 1: # 64-bit
        return offset + 8
    elif wire_type == 2: # Length-delimited
        length, content_start = decode_varint(data, offset)
        return content_start + length
    elif wire_type == 5: # 32-bit
        return offset + 4
    else:
        raise ValueError(f"Unknown wire type: {wire_type}")

def remove_field(data: bytes, target_field_num: int) -> bytes:
    """Remove all occurrences of target_field_num from protobuf message."""
    result = bytearray()
    offset = 0
    length = len(data)
    
    while offset < length:
        start_offset = offset
        try:
            tag, new_offset = decode_varint(data, offset)
        except ValueError:
            break # End of stream or broken

        wire_type = tag & 7
        field_num = tag >> 3
        
        # Calculate end of this field
        try:
            next_offset = skip_field(data, new_offset, wire_type)
        except Exception:
             # If we can't parse field, stop to be safe
             break

        if field_num == target_field_num:
            # Skip (don't add to result)
            pass
        else:
            # Keep
            result.extend(data[start_offset:next_offset])
        
        offset = next_offset
        
    return bytes(result)

# ---------------------------------------------------------------------------
# Process Info
# ---------------------------------------------------------------------------

@dataclass
class AntigravityProcessInfo:
    pid: int
    exe: str
    cmdline: List[str] = field(default_factory=list)

def find_antigravity_processes() -> List[AntigravityProcessInfo]:
    """Find all running Antigravity main processes (exclude helpers)."""
    found = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                info = proc.info
                name = (info.get('name') or '').lower()
                exe = info.get('exe') or ''
                cmdline = info.get('cmdline') or []

                is_target = False
                if sys.platform == "win32":
                    is_target = name == "antigravity.exe"
                elif sys.platform == "darwin":
                    is_target = "antigravity.app" in exe.lower()
                else:
                    is_target = name == "antigravity"

                if not is_target:
                    continue

                # Exclude helper/child processes
                cmd_str = " ".join(cmdline).lower()
                if any(marker in cmd_str for marker in [
                    "--type=", "helper", "crashpad", "gpu-process", "utility",
                    "renderer", "plugin", "sandbox", "audio"
                ]):
                    continue

                found.append(AntigravityProcessInfo(info['pid'], exe, cmdline))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Error scanning processes: {e}")
    return found


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@dataclass
class AntigravitySnapshot:
    exe_path: Optional[Path] = None
    db_path: Optional[Path] = None
    storage_path: Optional[Path] = None
    reusable_args: List[str] = field(default_factory=list)


def capture_snapshot() -> AntigravitySnapshot:
    snap = AntigravitySnapshot()
    procs = find_antigravity_processes()

    # --- exe path ---
    for p in procs:
        if p.exe and os.path.isfile(p.exe):
            snap.exe_path = Path(p.exe)
            break
    if not snap.exe_path:
        snap.exe_path = _find_exe_on_disk()

    # --- reusable args ---
    for p in procs:
        for i, arg in enumerate(p.cmdline):
            if arg in ("--user-data-dir", "--extensions-dir"):
                if i + 1 < len(p.cmdline):
                    snap.reusable_args.extend([arg, p.cmdline[i + 1]])
            elif arg.startswith("--user-data-dir=") or arg.startswith("--extensions-dir="):
                snap.reusable_args.append(arg)

    # --- db + storage path ---
    user_data_dir = _extract_user_data_dir(procs)
    if user_data_dir:
        candidate = user_data_dir / "User" / "globalStorage"
        if candidate.exists():
            snap.db_path = candidate / "state.vscdb"
            snap.storage_path = candidate / "storage.json"
            return snap

    if snap.exe_path:
        portable = snap.exe_path.parent / "data" / "user-data" / "User" / "globalStorage"
        if portable.exists():
            snap.db_path = portable / "state.vscdb"
            snap.storage_path = portable / "storage.json"
            return snap

    gs = _standard_global_storage()
    if gs:
        snap.db_path = gs / "state.vscdb"
        snap.storage_path = gs / "storage.json"

    return snap


def _extract_user_data_dir(procs: List[AntigravityProcessInfo]) -> Optional[Path]:
    for p in procs:
        for i, arg in enumerate(p.cmdline):
            if arg == "--user-data-dir" and i + 1 < len(p.cmdline):
                path = Path(p.cmdline[i + 1])
                if path.exists():
                    return path
            elif arg.startswith("--user-data-dir="):
                parts = arg.split("=", 1)
                if len(parts) == 2:
                    path = Path(parts[1])
                    if path.exists():
                        return path
    return None


def _find_exe_on_disk() -> Optional[Path]:
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "Antigravity.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Antigravity" / "Antigravity.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Antigravity" / "Antigravity.exe",
        ]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Antigravity.app/Contents/MacOS/Antigravity")]
    else:
        candidates = [Path("/usr/bin/antigravity")]

    for c in candidates:
        if c.exists():
            return c
    return None


def _standard_global_storage() -> Optional[Path]:
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if appdata:
            gs = Path(appdata) / "Antigravity" / "User" / "globalStorage"
            return gs
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Antigravity" / "User" / "globalStorage"
    elif sys.platform == "linux":
        return Path.home() / ".config" / "Antigravity" / "User" / "globalStorage"
    return None


def get_antigravity_db_path() -> Optional[Path]:
    snap = capture_snapshot()
    return snap.db_path

def get_storage_json_path() -> Optional[Path]:
    snap = capture_snapshot()
    return snap.storage_path


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def close_antigravity():
    logger.info("Closing Antigravity processes…")
    procs = find_antigravity_processes()
    if not procs:
        logger.info("No Antigravity processes found.")
        return

    live = []
    for info in procs:
        try:
            live.append(psutil.Process(info.pid))
        except psutil.NoSuchProcess:
            pass

    for p in live:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass

    gone, alive = psutil.wait_procs(live, timeout=5)

    if alive:
        logger.warning(f"Force killing {len(alive)} lingering processes…")
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=3)

    time.sleep(0.3)
    logger.info("Antigravity closed.")


def launch_antigravity(
    exe_path: Optional[Path] = None,
    extra_args: Optional[List[str]] = None,
):
    """Launch Antigravity using correct strategy (Protocol vs Direct)."""
    has_args = bool(extra_args)

    if has_args and exe_path and exe_path.exists():
        cmd: List[str] = [str(exe_path)] + list(extra_args)
        logger.info(f"Launching (direct): {' '.join(cmd)}")
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                cwd=str(exe_path.parent),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            subprocess.Popen(cmd, cwd=str(exe_path.parent), start_new_session=True)
    else:
        logger.info("Launching via protocol handler: antigravity://")
        if sys.platform == "win32":
            subprocess.Popen(
                ["cmd", "/C", "start", "antigravity://"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "antigravity://"])
        else:
            subprocess.Popen(["xdg-open", "antigravity://"])


# ---------------------------------------------------------------------------
# Device Fingerprint
# ---------------------------------------------------------------------------

def generate_device_profile() -> dict:
    return {
        "machineId": f"auth0|user_{secrets.token_hex(16)}",
        "macMachineId": str(uuid.uuid4()),
        "devDeviceId": str(uuid.uuid4()),
        "sqmId": "{" + str(uuid.uuid4()).upper() + "}",
    }


def write_device_profile(
    profile: dict,
    storage_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
):
    if storage_path and storage_path.exists():
        try:
            data = json.loads(storage_path.read_text(encoding="utf-8"))
            if "telemetry" not in data or not isinstance(data.get("telemetry"), dict):
                data["telemetry"] = {}

            data["telemetry"].update({
                "machineId": profile["machineId"],
                "macMachineId": profile["macMachineId"],
                "devDeviceId": profile["devDeviceId"],
                "sqmId": profile["sqmId"],
            })
            data["telemetry.machineId"] = profile["machineId"]
            data["telemetry.macMachineId"] = profile["macMachineId"]
            data["telemetry.devDeviceId"] = profile["devDeviceId"]
            data["telemetry.sqmId"] = profile["sqmId"]
            data["storage.serviceMachineId"] = profile["devDeviceId"]
            
            storage_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write storage.json: {e}")

    if db_path and db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute(
                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                ("storage.serviceMachineId", profile["devDeviceId"]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update state.vscdb: {e}")


# ---------------------------------------------------------------------------
# Token Injection (Dual Format Strategy)
# ---------------------------------------------------------------------------

def _create_oauth_fields_only(access_token: str, refresh_token: str, expiry: int) -> Tuple[bytes, bytes]:
    """Helper to create raw protobuf fields for Email and OAuthTokenInfo"""
    # Note: Email not passed here, handled by caller
    
    # OAuthTokenInfo (Field 6 content)
    f1 = encode_string(1, access_token)
    f2 = encode_string(2, "Bearer")
    f3 = encode_string(3, refresh_token)
    ts_inner = encode_varint((1 << 3) | 0) + encode_varint(expiry)
    f4 = encode_len_delim(4, ts_inner)
    oauth_info = f1 + f2 + f3 + f4
    
    return oauth_info

def inject_token_new_format(cursor: sqlite3.Cursor, access_token: str, refresh_token: str, expiry: int):
    """
    New Format (>= 1.16.5): antigravityUnifiedStateSync.oauthToken
    Structure: Outer -> Inner -> Base64(Inner2) -> Base64(OAuthTokenInfo)
    """
    oauth_info_raw = _create_oauth_fields_only(access_token, refresh_token, expiry)
    oauth_info_b64 = base64.b64encode(oauth_info_raw).decode("utf-8")

    inner2 = encode_string(1, oauth_info_b64)
    inner = encode_string(1, "oauthTokenInfoSentinelKey") + encode_len_delim(2, inner2)
    outer = encode_len_delim(1, inner)
    outer_b64 = base64.b64encode(outer).decode("utf-8")

    cursor.execute(
        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
        ("antigravityUnifiedStateSync.oauthToken", outer_b64),
    )
    cursor.execute(
        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
        ("antigravityOnboarding", "true"),
    )
    logger.info("Injected NEW format token")


def inject_token_old_format(cursor: sqlite3.Cursor, access_token: str, refresh_token: str, expiry: int, email: str = ""):
    """
    Old Format (< 1.16.5): jetskiStateSync.agentManagerInitState
    Structure: Protobuf Blob containing:
      Field 1: UserID (String) - We remove this to force session refresh
      Field 2: Email (String)  - We replace this
      Field 6: OAuthTokenInfo  - We replace this
      
    This function ONLY updates if the key already exists (Dual Injection strategy).
    """
    try:
        cursor.execute("SELECT value FROM ItemTable WHERE key = ?", ("jetskiStateSync.agentManagerInitState",))
        row = cursor.fetchone()
        if not row:
            logger.info("Old format key not found, skipping old format injection.")
            return

        current_b64 = row[0]
        if not current_b64:
             return

        blob = base64.b64decode(current_b64)
        
        # 1. Remove old fields
        blob = remove_field(blob, 1) # UserID
        blob = remove_field(blob, 2) # Email
        blob = remove_field(blob, 6) # OAuthTokenInfo
        
        # 2. Append new fields
        # Field 2: Email
        new_email_field = encode_string(2, email)
        
        # Field 6: OAuthTokenInfo
        # Re-use helper. Note that this time we need to wrap it in Field 6 tag
        oauth_info_raw = _create_oauth_fields_only(access_token, refresh_token, expiry)
        new_token_field = encode_len_delim(6, oauth_info_raw)
        
        final_blob = blob + new_email_field + new_token_field
        final_b64 = base64.b64encode(final_blob).decode("utf-8")
        
        cursor.execute(
            "UPDATE ItemTable SET value = ? WHERE key = ?",
            (final_b64, "jetskiStateSync.agentManagerInitState")
        )
        logger.info("Injected OLD format token (update existing)")
        
    except Exception as e:
        logger.error(f"Failed to inject old format token: {e}")


def inject_token(db_path: Path, access_token: str, refresh_token: str, expiry: int, email: str = "user@example.com"):
    """Main injection entry – backs up DB then tries DUAL INJECTION."""
    if not db_path:
        raise ValueError("db_path is None")

    # Backup
    try:
        import shutil
        if db_path.exists():
            shutil.copy2(db_path, db_path.with_suffix(".vscdb.backup"))
    except Exception as e:
        logger.warning(f"Backup failed (non-fatal): {e}")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        
        # Strategy: ALWAYS inject new format, OPTIONALLY update old format if present
        inject_token_new_format(cur, access_token, refresh_token, expiry)
        inject_token_old_format(cur, access_token, refresh_token, expiry, email)
        
        conn.commit()
        logger.info(f"Token injection completed for {db_path}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Token injection transaction failed: {e}")
        raise e
    finally:
        conn.close()

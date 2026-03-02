"""
Proxy-specific request logger.

Stores API proxy request logs in an in-memory ring buffer.
These are separate from the main backend request logs (services/logger.py).
"""

import time
import asyncio
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any
from typing import Any


@dataclass
class ProxyLogEntry:
    """A single proxy request log entry."""
    id: int = 0
    timestamp: float = 0.0
    method: str = ""           # POST
    path: str = ""             # /v1/chat/completions or /v1/messages
    api_format: str = ""       # "openai" or "anthropic"
    model: str = ""            # gemini-2.5-pro
    original_model: str = ""   # original model before mapping (empty if no mapping)
    stream: bool = False
    status_code: int = 0
    duration_ms: float = 0.0
    account_email: str = ""    # which pool account was used
    account_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""            # error message if failed
    client_ip: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp_iso"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(self.timestamp)
        ) + f".{int(self.timestamp * 1000) % 1000:03d}Z"
        return d


class ProxyLogger:
    """In-memory ring buffer for proxy request logs."""

    def __init__(self, max_entries: int = 500):
        self._entries: deque[ProxyLogEntry] = deque(maxlen=max_entries)
        self._counter: int = 0
        # Removing asyncio.Lock here because ProxyLogger needs to be usable 
        # instantly synchronously in the sync endpoints or logging parts, 
        # and list appends are largely thread-safe in CPython anyway.
        # But for correctness, we'll keep threading.Lock. Wait, if it's already threading.Lock
        # there's no harm in keeping it for async if it doesn't block. 
        # Let me just revert my thought and keep threading.Lock as it's safe for 
        # fast memory operations without await.
        import threading
        self._lock = threading.Lock()

    def log(
        self,
        method: str,
        path: str,
        api_format: str,
        model: str,
        stream: bool,
        status_code: int,
        duration_ms: float,
        account_email: str = "",
        account_id: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: str = "",
        client_ip: str = "",
        original_model: str = "",
    ) -> ProxyLogEntry:
        with self._lock:
            self._counter += 1
            entry = ProxyLogEntry(
                id=self._counter,
                timestamp=time.time(),
                method=method,
                path=path,
                api_format=api_format,
                model=model,
                original_model=original_model,
                stream=stream,
                status_code=status_code,
                duration_ms=duration_ms,
                account_email=account_email,
                account_id=account_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=error,
                client_ip=client_ip,
            )
            self._entries.append(entry)
            return entry

    def get_logs(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get logs in reverse chronological order."""
        with self._lock:
            entries = list(self._entries)
        entries.reverse()
        return [e.to_dict() for e in entries[offset:offset + limit]]

    def get_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()



# Singleton instance
_proxy_logger = ProxyLogger()


def get_proxy_logger() -> ProxyLogger:
    return _proxy_logger

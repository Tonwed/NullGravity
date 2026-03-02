"""
CloudCode Reverse Proxy Service

Transparent HTTP/HTTPS reverse proxy for cloudcode-pa.googleapis.com.
Intercepts requests from the Antigravity Language Server, replaces the
Authorization header with a token from the account pool, and forwards
to the real Google endpoint.

Token rotation: when an account's quota is exhausted (429 / RESOURCE_EXHAUSTED),
automatically switches to the next available account.
"""

import asyncio
import hashlib
import logging
import random
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx

from database.connection import async_session
from models.account import Account
from models.credential import OAuthCredential
from models.settings import AppSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger("cloudcode_proxy")

# ---------------------------------------------------------------------------
# Proxy state
# ---------------------------------------------------------------------------

UPSTREAM_DAILY = "https://daily-cloudcode-pa.googleapis.com"
UPSTREAM_PROD = "https://cloudcode-pa.googleapis.com"
DEFAULT_PROXY_PORT = 9090

_proxy_server: "uvicorn.Server | None" = None
_proxy_state: dict = {
    "running": False,
    "port": DEFAULT_PROXY_PORT,
    "upstream": UPSTREAM_DAILY,
    "total_requests": 0,
    "total_rotations": 0,
    "started_at": None,
    "current_account_email": None,
    "current_account_id": None,
}

# Shared httpx client — created on proxy start, closed on stop
_http_client: httpx.AsyncClient | None = None


def get_proxy_state() -> dict:
    return {**_proxy_state}


# ---------------------------------------------------------------------------
# Account Pool
# ---------------------------------------------------------------------------

class AccountPool:
    """Manages a rotating pool of Antigravity OAuth accounts.

    Tokens are read directly from DB on every get_current() call,
    so auto-refreshed tokens are used immediately without any sync step.
    Only rotation state (index, exhausted, rate-limited) is kept in memory.

    Supports three scheduling modes:
    - cache_first: Bind session→account, wait on rate limit (maximize Prompt Cache)
    - balance:     Bind session→account, hot-switch on rate limit (default)
    - performance: No binding, random rotation (high concurrency)
    """

    MAX_BINDINGS = 1000
    BINDING_TTL = 1800  # 30 minutes

    def __init__(self):
        self._current_index: int = 0
        self._exhausted: set[str] = set()  # account IDs marked exhausted
        self._rate_limited: dict[str, float] = {}  # account_id -> until_timestamp
        self._lock = asyncio.Lock()
        self._account_ids: list[str] = []  # ordered list of account IDs for stable indexing
        # Cooldown tracking
        self._last_request_time: dict[str, float] = {}  # account_id -> timestamp
        # Session binding (for cache_first & balance modes)
        self._session_bindings: dict[str, str] = {}  # session_fingerprint -> account_id
        self._binding_timestamps: dict[str, float] = {}  # session_fingerprint -> last_access

    async def refresh(self):
        """Reload the account ID list and clear stale marks.

        Only updates the ordered ID list for rotation indexing.
        Tokens are always read fresh from DB in get_current().
        """
        async with async_session() as session:
            result = await session.execute(
                select(Account.id)
                .where(Account.status == "active")
                .where(Account.is_forbidden == False)
                .where(Account.is_disabled == False)
                .order_by(Account.email)
            )
            ids = [row[0] for row in result.all()]

        async with self._lock:
            self._account_ids = ids
            if self._current_index >= len(ids):
                self._current_index = 0
            valid = set(ids)
            self._exhausted = self._exhausted & valid
            self._rate_limited = {
                k: v for k, v in self._rate_limited.items()
                if k in valid and v > time.time()
            }
            # Clean bindings referencing removed accounts
            self._session_bindings = {
                k: v for k, v in self._session_bindings.items()
                if v in valid
            }
            self._binding_timestamps = {
                k: v for k, v in self._binding_timestamps.items()
                if k in self._session_bindings
            }
            logger.info(f"Account pool refreshed: {len(ids)} accounts available")

    async def _read_account(self, account_id: str) -> dict | None:
        """Read a single account with fresh token directly from DB."""
        async with async_session() as session:
            result = await session.execute(
                select(Account)
                .options(selectinload(Account.credentials))
                .where(Account.id == account_id)
            )
            acc = result.scalar_one_or_none()
            if not acc:
                return None
            ag_cred = next(
                (c for c in acc.credentials if c.client_type == "antigravity" and c.access_token),
                None,
            )
            if not ag_cred:
                return None
            return {
                "id": acc.id,
                "email": acc.email,
                "access_token": ag_cred.access_token,
                "project_id": ag_cred.project_id,
            }

    async def _get_setting(self, key: str, default: str = "") -> str:
        """Read a setting value from DB."""
        async with async_session() as session:
            result = await session.execute(
                select(AppSettings.value).where(AppSettings.key == key)
            )
            row = result.scalar_one_or_none()
            return row if row is not None else default

    async def _get_cooldown_seconds(self) -> float:
        """Get the cooldown interval from settings."""
        val = await self._get_setting("pool_cooldown", "0")
        try:
            return max(0.0, float(val))
        except (ValueError, TypeError):
            return 0.0

    async def _get_schedule_mode(self) -> str:
        """Get the scheduling mode from settings."""
        val = await self._get_setting("pool_schedule_mode", "balance")
        if val in ("cache_first", "balance", "performance"):
            return val
        return "balance"

    async def wait_cooldown(self, account_id: str):
        """Wait for account cooldown to complete before sending request."""
        cooldown = await self._get_cooldown_seconds()
        if cooldown <= 0:
            return
        last = self._last_request_time.get(account_id, 0)
        remaining = cooldown - (time.time() - last)
        if remaining > 0:
            logger.debug(f"Cooldown wait {remaining:.1f}s for {account_id[:8]}...")
            await asyncio.sleep(remaining)

    def mark_request(self, account_id: str):
        """Mark the time an account sent a request."""
        self._last_request_time[account_id] = time.time()

    @staticmethod
    def get_session_fingerprint(request) -> str:
        """Generate a session fingerprint from request for account binding."""
        ip = ""
        if hasattr(request, "headers"):
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip and hasattr(request, "client") and request.client:
            ip = request.client.host
        if not ip:
            ip = "unknown"
        ua = ""
        if hasattr(request, "headers"):
            ua = request.headers.get("user-agent", "")
        raw = f"{ip}|{ua}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _clean_stale_bindings(self):
        """Remove expired bindings (LRU, max 1000, TTL 30min)."""
        now = time.time()
        # Remove expired entries
        expired = [k for k, ts in self._binding_timestamps.items()
                   if now - ts > self.BINDING_TTL]
        for k in expired:
            self._session_bindings.pop(k, None)
            self._binding_timestamps.pop(k, None)
        # If still over limit, remove oldest
        if len(self._session_bindings) > self.MAX_BINDINGS:
            sorted_keys = sorted(self._binding_timestamps, key=self._binding_timestamps.get)
            to_remove = sorted_keys[:len(self._session_bindings) - self.MAX_BINDINGS]
            for k in to_remove:
                self._session_bindings.pop(k, None)
                self._binding_timestamps.pop(k, None)

    def _assign_least_loaded(self) -> str:
        """Assign the account with the fewest bound sessions."""
        binding_counts = Counter(self._session_bindings.values())
        candidates = [aid for aid in self._account_ids if aid not in self._exhausted]
        if not candidates:
            candidates = list(self._account_ids)
        candidates.sort(key=lambda aid: binding_counts.get(aid, 0))
        return candidates[0] if candidates else self._account_ids[0]

    def _is_available(self, account_id: str) -> bool:
        """Check if an account is available (not exhausted, not rate-limited)."""
        if account_id in self._exhausted:
            return False
        if account_id in self._rate_limited and self._rate_limited[account_id] > time.time():
            return False
        return True

    def _find_available_fallback(self) -> str | None:
        """Find any available account (for hot-switching in balance mode)."""
        now = time.time()
        for aid in self._account_ids:
            if aid not in self._exhausted and (aid not in self._rate_limited or self._rate_limited[aid] <= now):
                return aid
        return None

    async def get_current(self, request=None) -> dict | None:
        """Get the current account with a fresh token from DB.

        Uses the scheduling mode to determine account selection:
        - cache_first: Bind session, wait on rate limit
        - balance: Bind session, hot-switch on rate limit
        - performance: Random selection, no binding
        """
        mode = await self._get_schedule_mode()

        async with self._lock:
            if not self._account_ids:
                return None

            self._clean_stale_bindings()
            now = time.time()

            if mode == "performance" or request is None:
                # Performance mode: random selection from available accounts
                available = [aid for aid in self._account_ids if self._is_available(aid)]
                if not available:
                    # All exhausted — clear and use all
                    self._exhausted.clear()
                    self._rate_limited.clear()
                    available = list(self._account_ids)
                aid = random.choice(available)
                acc = await self._read_account(aid)
                if acc:
                    _proxy_state["current_account_email"] = acc["email"]
                    _proxy_state["current_account_id"] = acc["id"]
                    return acc
                return None

            # Session-bound modes (cache_first / balance)
            fp = self.get_session_fingerprint(request)
            bound_aid = self._session_bindings.get(fp)

            if bound_aid and bound_aid in self._account_ids:
                self._binding_timestamps[fp] = now

                if self._is_available(bound_aid):
                    acc = await self._read_account(bound_aid)
                    if acc:
                        _proxy_state["current_account_email"] = acc["email"]
                        _proxy_state["current_account_id"] = acc["id"]
                        return acc

                # Bound account is unavailable
                if mode == "cache_first":
                    # Cache First: wait for rate limit to clear (don't switch)
                    if bound_aid in self._rate_limited:
                        remaining = self._rate_limited[bound_aid] - now
                        if remaining > 0:
                            logger.debug(f"Cache-first: waiting {remaining:.0f}s for rate limit on {bound_aid[:8]}...")
                            # Release lock while waiting
                            self._lock.release()
                            try:
                                await asyncio.sleep(remaining)
                            finally:
                                await self._lock.acquire()
                        # After wait, try again
                        self._rate_limited.pop(bound_aid, None)
                        acc = await self._read_account(bound_aid)
                        if acc:
                            _proxy_state["current_account_email"] = acc["email"]
                            _proxy_state["current_account_id"] = acc["id"]
                            return acc

                    # If exhausted (permanent), reassign
                    if bound_aid in self._exhausted:
                        new_aid = self._assign_least_loaded()
                        self._session_bindings[fp] = new_aid
                        self._binding_timestamps[fp] = now
                        acc = await self._read_account(new_aid)
                        if acc:
                            _proxy_state["current_account_email"] = acc["email"]
                            _proxy_state["current_account_id"] = acc["id"]
                            return acc

                else:  # balance mode
                    # Balance: hot-switch to available account (temporary, don't update binding)
                    fallback_aid = self._find_available_fallback()
                    if fallback_aid:
                        acc = await self._read_account(fallback_aid)
                        if acc:
                            _proxy_state["current_account_email"] = acc["email"]
                            _proxy_state["current_account_id"] = acc["id"]
                            return acc

            # No binding or binding invalid — assign least loaded
            new_aid = self._assign_least_loaded()
            self._session_bindings[fp] = new_aid
            self._binding_timestamps[fp] = now
            acc = await self._read_account(new_aid)
            if acc:
                _proxy_state["current_account_email"] = acc["email"]
                _proxy_state["current_account_id"] = acc["id"]
                return acc

            # Final fallback: clear all marks and try first
            self._exhausted.clear()
            self._rate_limited.clear()
            if self._account_ids:
                self._current_index = 0
                acc = await self._read_account(self._account_ids[0])
                if acc:
                    _proxy_state["current_account_email"] = acc["email"]
                    _proxy_state["current_account_id"] = acc["id"]
                    return acc
            return None

    async def rotate(self, failed_account_id: str, reason: str = "exhausted") -> dict | None:
        """Mark current account as exhausted/rate-limited and rotate to next."""
        async with self._lock:
            if reason == "rate_limited":
                self._rate_limited[failed_account_id] = time.time() + 60
            else:
                self._exhausted.add(failed_account_id)
            self._current_index = (self._current_index + 1) % max(len(self._account_ids), 1)
            _proxy_state["total_rotations"] += 1

        # get_current() will read fresh from DB
        account = await self.get_current()
        if account:
            logger.info(f"Rotated to account: {account['email']} (reason: {reason})")
        else:
            logger.warning("No available accounts after rotation")
        return account

    @property
    def size(self) -> int:
        return len(self._account_ids)

    @property
    def available_count(self) -> int:
        now = time.time()
        return sum(
            1 for aid in self._account_ids
            if aid not in self._exhausted
            and (aid not in self._rate_limited or self._rate_limited[aid] <= now)
        )

    def get_account_statuses(self) -> list[dict]:
        """Get status of each account in the pool for the status API."""
        now = time.time()
        statuses = []
        for aid in self._account_ids:
            if aid in self._exhausted:
                status = "exhausted"
                remaining = None
            elif aid in self._rate_limited and self._rate_limited[aid] > now:
                status = "rate_limited"
                remaining = int(self._rate_limited[aid] - now)
            else:
                status = "available"
                remaining = None
            statuses.append({
                "id": aid,
                "status": status,
                "remaining_seconds": remaining,
            })
        return statuses

    async def get_account_statuses_with_email(self) -> list[dict]:
        """Get status of each account including email for the status API.

        Always reads active accounts from DB so it works even when proxy is stopped.
        """
        now = time.time()
        async with async_session() as session:
            result = await session.execute(
                select(Account.id, Account.email)
                .where(Account.status == "active")
                .where(Account.is_forbidden == False)
                .where(Account.is_disabled == False)
                .order_by(Account.email)
            )
            db_accounts = result.all()

        statuses = []
        for aid, email in db_accounts:
            if aid in self._exhausted:
                status = "exhausted"
                remaining = None
            elif aid in self._rate_limited and self._rate_limited[aid] > now:
                status = "rate_limited"
                remaining = int(self._rate_limited[aid] - now)
            else:
                status = "available"
                remaining = None
            statuses.append({
                "id": aid,
                "email": email,
                "status": status,
                "remaining_seconds": remaining,
            })
        return statuses


_pool = AccountPool()


def get_pool() -> AccountPool:
    return _pool


def _get_client() -> httpx.AsyncClient:
    """Get the shared httpx client, raising if proxy not started."""
    if _http_client is None:
        raise RuntimeError("Proxy not started — no HTTP client available")
    return _http_client


# ---------------------------------------------------------------------------
# Proxy request handler (non-streaming, for normal requests)
# ---------------------------------------------------------------------------

async def handle_proxy_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes | None,
    query_string: str = "",
) -> tuple[int, dict[str, str], bytes]:
    """
    Handle a proxied request (non-streaming):
    1. Get current account from pool
    2. Replace Authorization header
    3. Forward to upstream
    4. If 429/RESOURCE_EXHAUSTED, rotate and retry
    """
    _proxy_state["total_requests"] += 1
    upstream = _proxy_state["upstream"]
    max_retries = min(_pool.size, 5)  # Don't retry more than pool size
    client = _get_client()

    for attempt in range(max(max_retries, 1)):
        account = await _pool.get_current()
        if not account:
            return 503, {"Content-Type": "application/json"}, b'{"error":"No available accounts in pool"}'

        # Build upstream URL
        url = f"{upstream}/{path.lstrip('/')}"
        if query_string:
            url += f"?{query_string}"

        # Replace Authorization header + inject correct gRPC fingerprint headers
        from utils.fingerprint import get_fingerprint
        fp = get_fingerprint()
        fwd_headers = {k: v for k, v in headers.items()
                       if k.lower() not in ("host", "authorization", "content-length")}
        fwd_headers["Authorization"] = f"Bearer {account['access_token']}"
        fwd_headers["x-goog-api-client"] = fp.x_goog_api_client
        project_id = account.get("project_id", "")
        if project_id:
            fwd_headers["x-goog-request-params"] = f"project={project_id}"
        elif "x-goog-request-params" not in fwd_headers:
            fwd_headers["x-goog-request-params"] = ""

        try:
            resp = await client.request(
                method=method,
                url=url,
                headers=fwd_headers,
                content=body,
            )

            resp_headers = dict(resp.headers)
            # Remove hop-by-hop headers
            for h in ("transfer-encoding", "content-encoding", "content-length"):
                resp_headers.pop(h, None)

            # Check for quota exhaustion
            if resp.status_code == 429:
                logger.warning(f"Account {account['email']} rate limited (429), rotating...")
                await _pool.rotate(account["id"], reason="rate_limited")
                continue

            if resp.status_code == 403:
                body_text = resp.content.decode("utf-8", errors="replace")
                if "RESOURCE_EXHAUSTED" in body_text or "quota" in body_text.lower():
                    logger.warning(f"Account {account['email']} quota exhausted, rotating...")
                    await _pool.rotate(account["id"], reason="exhausted")
                    continue

            return resp.status_code, resp_headers, resp.content

        except httpx.TimeoutException:
            logger.error(f"Upstream timeout for {url}")
            return 504, {"Content-Type": "application/json"}, b'{"error":"Upstream timeout"}'
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return 502, {"Content-Type": "application/json"}, f'{{"error":"{str(e)}"}}'.encode()

    # All retries exhausted
    return 503, {"Content-Type": "application/json"}, b'{"error":"All accounts exhausted, no quota available"}'


# ---------------------------------------------------------------------------
# Streaming proxy request handler (for SSE / AI responses)
# ---------------------------------------------------------------------------

async def handle_streaming_proxy_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes | None,
    query_string: str = "",
) -> tuple[int, dict[str, str], AsyncIterator[bytes]] | tuple[int, dict[str, str], bytes]:
    """
    Handle a proxied request with streaming support:
    Returns either (status, headers, async_iterator) for streaming
    or (status, headers, bytes) for error cases.
    """
    _proxy_state["total_requests"] += 1
    upstream = _proxy_state["upstream"]
    max_retries = min(_pool.size, 5)
    client = _get_client()

    for attempt in range(max(max_retries, 1)):
        account = await _pool.get_current()
        if not account:
            return 503, {"Content-Type": "application/json"}, b'{"error":"No available accounts in pool"}'

        # Build upstream URL
        url = f"{upstream}/{path.lstrip('/')}"
        if query_string:
            url += f"?{query_string}"

        # Replace Authorization header + inject correct gRPC fingerprint headers
        from utils.fingerprint import get_fingerprint
        fp = get_fingerprint()
        fwd_headers = {k: v for k, v in headers.items()
                       if k.lower() not in ("host", "authorization", "content-length")}
        fwd_headers["Authorization"] = f"Bearer {account['access_token']}"
        fwd_headers["x-goog-api-client"] = fp.x_goog_api_client
        project_id = account.get("project_id", "")
        if project_id:
            fwd_headers["x-goog-request-params"] = f"project={project_id}"
        elif "x-goog-request-params" not in fwd_headers:
            fwd_headers["x-goog-request-params"] = ""

        try:
            req = client.build_request(
                method=method,
                url=url,
                headers=fwd_headers,
                content=body,
            )
            resp = await client.send(req, stream=True)

            resp_headers = dict(resp.headers)
            for h in ("transfer-encoding", "content-encoding", "content-length"):
                resp_headers.pop(h, None)

            # For 429 / quota errors we need to read the body to check
            if resp.status_code == 429:
                await resp.aread()
                await resp.aclose()
                logger.warning(f"Account {account['email']} rate limited (429), rotating...")
                await _pool.rotate(account["id"], reason="rate_limited")
                continue

            if resp.status_code == 403:
                await resp.aread()
                body_text = resp.content.decode("utf-8", errors="replace")
                await resp.aclose()
                if "RESOURCE_EXHAUSTED" in body_text or "quota" in body_text.lower():
                    logger.warning(f"Account {account['email']} quota exhausted, rotating...")
                    await _pool.rotate(account["id"], reason="exhausted")
                    continue
                # Not a quota issue — return the 403 as bytes
                return resp.status_code, resp_headers, resp.content

            # Stream the response body
            async def stream_body(response: httpx.Response) -> AsyncIterator[bytes]:
                try:
                    async for chunk in response.aiter_bytes(4096):
                        yield chunk
                finally:
                    await response.aclose()

            return resp.status_code, resp_headers, stream_body(resp)

        except httpx.TimeoutException:
            logger.error(f"Upstream timeout for {url}")
            return 504, {"Content-Type": "application/json"}, b'{"error":"Upstream timeout"}'
        except Exception as e:
            logger.error(f"Proxy streaming error: {e}")
            if attempt == max_retries - 1:
                return 502, {"Content-Type": "application/json"}, f'{{"error":"{str(e)}"}}'.encode()
            continue

    # All retries exhausted
    return 503, {"Content-Type": "application/json"}, b'{"error":"All accounts exhausted, no quota available"}'


# ---------------------------------------------------------------------------
# Proxy server lifecycle
# ---------------------------------------------------------------------------

async def start_proxy(port: int = DEFAULT_PROXY_PORT, upstream: str = UPSTREAM_DAILY):
    """Start the reverse proxy HTTPS server."""
    global _proxy_server, _http_client

    if _proxy_server is not None:
        logger.warning("Proxy already running")
        return

    _proxy_state["port"] = port
    _proxy_state["upstream"] = upstream

    # Create shared httpx client (reuses TCP/TLS connections, enables HTTP/2 multiplexing)
    _http_client = httpx.AsyncClient(
        timeout=180.0,
        http2=True,
        verify=False,  # Important for internal proxying local TLS
        follow_redirects=False,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
    )

    # Refresh account pool
    await _pool.refresh()

    if _pool.size == 0:
        logger.warning("No accounts available for proxy pool")

    # Start a simple HTTP server (Language Server will connect via jetski.cloudCodeUrl)
    from .cloudcode_proxy_server import create_proxy_app

    proxy_app = create_proxy_app()

    import uvicorn
    config = uvicorn.Config(
        proxy_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    _proxy_state["running"] = True
    _proxy_state["started_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"CloudCode proxy started on 127.0.0.1:{port} → {upstream}")

    # Run in background
    asyncio.create_task(server.serve())
    _proxy_server = server


async def stop_proxy():
    """Stop the reverse proxy server."""
    global _proxy_server, _http_client

    if _proxy_server is None:
        return

    _proxy_server.should_exit = True
    _proxy_server = None
    _proxy_state["running"] = False
    _proxy_state["started_at"] = None
    _proxy_state["current_account_email"] = None
    _proxy_state["current_account_id"] = None

    # Close shared httpx client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None

    logger.info("CloudCode proxy stopped")

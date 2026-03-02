import os
import httpx
import logging
import time
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy import select
from models.settings import AppSettings

logger = logging.getLogger(__name__)

# Global cache
_cached_proxy_url: str | None = None
_proxy_enabled: bool = False
_proxy_status: dict = {"status": "unknown"}

def set_cached_proxy(url: str | None):
    global _cached_proxy_url
    _cached_proxy_url = url.strip().rstrip('/') if url else None
    if _cached_proxy_url:
        logger.info(f"Proxy URL updated: {_cached_proxy_url}")

def set_cached_proxy_enabled(enabled: bool):
    global _proxy_enabled
    _proxy_enabled = enabled
    logger.info(f"Proxy enabled: {enabled}")

def _resolve_proxy() -> str | None:
    """Resolve proxy URL from cache or environment."""
    # print(f"DEBUG: Proxy Resolve - Enabled: {_proxy_enabled}, URL: {_cached_proxy_url}")
    if _proxy_enabled and _cached_proxy_url:
        return _cached_proxy_url
    # If proxy disabled in settings, return None (let httpx use env or direct)
    return None

async def load_proxy_from_db(session):
    """Load proxy settings from DB into memory."""
    try:
        result = await session.execute(select(AppSettings).where(AppSettings.key.in_(["proxy_url", "proxy_enabled"])))
        settings = {s.key: s.value for s in result.scalars().all()}
        
        url = settings.get("proxy_url")
        enabled = settings.get("proxy_enabled", "false") == "true"
        
        set_cached_proxy(url)
        set_cached_proxy_enabled(enabled)
    except Exception as e:
        logger.error(f"Failed to load proxy settings: {e}")

async def get_proxy_status(force: bool = False):
    """Check proxy connectivity and IP info separately.
    
    Returns: {enabled, connected, latency_ms, ip, city, country, region, org, error, ip_error}
    - connected: proxy is reachable (basic connectivity test)
    - ip/city/country/etc: IP info from geo-lookup (may fail independently)
    - error: connectivity error (only if connected=False)
    - ip_error: IP lookup error (proxy works but IP query failed)
    """
    global _proxy_status

    if not _proxy_enabled or not _cached_proxy_url:
        return {"enabled": False, "connected": False}

    if not force and _proxy_status.get("enabled") is not None and _proxy_status.get("connected") is not None:
        return _proxy_status

    start = time.time()
    result: dict = {"enabled": True, "connected": False}

    try:
        # Build httpx client with proxy
        try:
            client = httpx.AsyncClient(proxy=_cached_proxy_url, timeout=10.0)
        except TypeError:
            proxies = {"all://": _cached_proxy_url}
            client = httpx.AsyncClient(proxies=proxies, timeout=10.0)

        async with client:
            # Phase 1: Test basic connectivity through the proxy
            try:
                conn_resp = await client.head("https://www.google.com", follow_redirects=True)
                latency_ms = round((time.time() - start) * 1000)
                result["connected"] = True
                result["latency_ms"] = latency_ms
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {str(e)}"
                _proxy_status = result
                return _proxy_status

            # Phase 2: Query IP info from multiple providers (fallback chain)
            ip_providers = [
                {
                    "url": "https://ipinfo.io/json",
                    "parse": lambda d: {
                        "ip": d.get("ip"),
                        "city": d.get("city"),
                        "region": d.get("region"),
                        "country": d.get("country"),
                        "org": d.get("org"),
                    },
                },
                {
                    "url": "http://ip-api.com/json/?fields=query,city,regionName,country,isp",
                    "parse": lambda d: {
                        "ip": d.get("query"),
                        "city": d.get("city"),
                        "region": d.get("regionName"),
                        "country": d.get("country"),
                        "org": d.get("isp"),
                    },
                },
                {
                    "url": "https://ipapi.co/json/",
                    "parse": lambda d: {
                        "ip": d.get("ip"),
                        "city": d.get("city"),
                        "region": d.get("region"),
                        "country": d.get("country_name"),
                        "org": d.get("org"),
                    },
                },
            ]

            ip_resolved = False
            ip_errors = []
            for provider in ip_providers:
                try:
                    resp = await client.get(provider["url"], follow_redirects=True)
                    if resp.status_code == 200:
                        data = resp.json()
                        geo = provider["parse"](data)
                        if geo.get("ip"):
                            result.update(geo)
                            ip_resolved = True
                            break
                    else:
                        ip_errors.append(f"{provider['url']}: HTTP {resp.status_code}")
                except Exception as e:
                    ip_errors.append(f"{provider['url']}: {type(e).__name__}")

            if not ip_resolved and ip_errors:
                result["ip_error"] = "; ".join(ip_errors)

    except Exception as e:
        result = {
            "enabled": True,
            "connected": False,
            "error": f"{type(e).__name__}: {str(e)}",
        }

    _proxy_status = result
    return _proxy_status

async def start_proxy_monitor():
    """Background task to monitor proxy status."""
    from database.connection import async_session
    from services.event import log_event

    last_success = None

    while True:
        try:
            status = await get_proxy_status(force=True)
            current_success = status.get("connected")
            
            # Detect change
            if last_success is not None and current_success != last_success:
                async with async_session() as session:
                    if current_success:
                        msg = f"Proxy connected: {status.get('ip', 'unknown')} ({status.get('country', '?')})"
                        await log_event(session, "proxy.change", msg, level="success", details=status)
                    else:
                        err = status.get("error", "Unknown error")
                        await log_event(session, "proxy.change", f"Proxy disconnected: {err}", level="error", details=status)
            
            last_success = current_success

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Proxy monitor error: {e}")
        await asyncio.sleep(60) # Check every minute

# Global Logging Hooks
async def _log_request_hook(request):
    try:
        # print(f"DEBUG: Request hook triggered for {request.url}")
        request.extensions['log_start_time'] = time.time()
    except: pass

async def _log_response_hook(response):
    try:
        req = response.request
        # print(f"DEBUG: Response hook triggered for {req.url} status {response.status_code}")
        start = req.extensions.get('log_start_time')
        duration = (time.time() - start) * 1000 if start else 0
        
        # Capture Request Body
        req_body_str = None
        try:
            # client.post(json=...) populated .content
            if hasattr(req, 'content') and req.content:
                 req_body_str = req.content.decode('utf-8', errors='replace')
        except: pass
        
        # Capture Response Body
        res_body_str = None
        ct = response.headers.get("content-type", "").lower()
        cl = response.headers.get("content-length")
        
        # Read body if JSON/Text and manageable size (<1MB)
        should_read = ("json" in ct or "text" in ct) and (not cl or int(cl) < 1000000)
        
        if should_read:
            try:
                 # Ensure content is read into memory
                 await response.aread()
                 res_body_str = response.content.decode('utf-8', errors='replace')
            except: 
                 res_body_str = "[Binary/Stream]"

        # Import locally to avoid circular imports if any
        from services.logger import save_log
        import asyncio

        # Extract account_id from request extensions
        acct_id = req.extensions.get('log_account_id')

        asyncio.create_task(save_log(
            method=req.method,
            path=str(req.url),
            status_code=response.status_code,
            duration_ms=duration,
            client_ip="Backend",
            headers=dict(req.headers),
            request_body=req_body_str,
            response_body=res_body_str,
            error_detail=None if response.is_success else f"Status {response.status_code}",
            account_id=acct_id
        ))
    except Exception as e:
        print(f"DEBUG: Failed to log: {e}")

@asynccontextmanager
async def get_http_client(
    timeout: float = 30.0,
    account_id: str | None = None,
    **kwargs,
) -> AsyncIterator[httpx.AsyncClient]:
    proxy_url = _resolve_proxy()

    # Create hooks that inject account_id into request extensions
    async def _account_request_hook(request):
        try:
            request.extensions['log_start_time'] = time.time()
            if account_id:
                request.extensions['log_account_id'] = account_id
        except: pass

    hooks = {'request': [_account_request_hook], 'response': [_log_response_hook]}
    
    if 'event_hooks' in kwargs:
         eh = kwargs.pop('event_hooks')
         hooks['request'].extend(eh.get('request', []))
         hooks['response'].extend(eh.get('response', []))

    client_kwargs = {
        "timeout": timeout,
        "event_hooks": hooks,
        **kwargs
    }
    
    if proxy_url:
        try:
            client = httpx.AsyncClient(proxy=proxy_url, **client_kwargs)
        except TypeError:
            client = httpx.AsyncClient(proxies=proxy_url, **client_kwargs)
    else:
        client = httpx.AsyncClient(**client_kwargs)

    async with client as c:
        yield c


# ---------------------------------------------------------------------------
# Go TLS Fingerprint Client (curl_cffi)
# ---------------------------------------------------------------------------
# 逆向分析: language_server_windows_x64.exe 使用 Go 1.27 crypto/tls
# 使用 curl_cffi 的自定义 JA3 功能精确匹配 Go TLS 指纹
# ---------------------------------------------------------------------------

from curl_cffi.requests import AsyncSession as CurlAsyncSession


class _ChromeSession:
    """Thin wrapper over curl_cffi AsyncSession with request/response logging."""

    def __init__(self, session: CurlAsyncSession, account_id: str | None = None):
        self._s = session
        self._account_id = account_id

    async def get(self, url, *, headers=None, params=None, follow_redirects=True, **kw):
        start = time.time()
        r = await self._s.get(
            str(url), headers=headers, params=params,
            allow_redirects=follow_redirects, **kw,
        )
        await self._log(r, start, "GET", str(url))
        return r

    async def post(self, url, *, json=None, data=None, headers=None, **kw):
        start = time.time()
        req_body_str = None
        if json is not None:
            import json as _json
            req_body_str = _json.dumps(json)
        r = await self._s.post(
            str(url), json=json, data=data, headers=headers, **kw,
        )
        await self._log(r, start, "POST", str(url), req_body_str)
        return r

    async def head(self, url, *, follow_redirects=True, **kw):
        return await self._s.head(str(url), allow_redirects=follow_redirects, **kw)

    async def post_stream(self, url, *, json=None, headers=None, **kw):
        """POST with stream=True for real-time SSE. Caller must close() when done."""
        r = await self._s.post(str(url), json=json, headers=headers, stream=True, **kw)
        return r

    async def close(self):
        """Close the underlying curl_cffi session."""
        try:
            await self._s.close()
        except Exception:
            pass

    async def _log(self, resp, start, method, url, req_body=None):
        try:
            duration = (time.time() - start) * 1000
            res_body = None
            ct = resp.headers.get("content-type", "").lower() if resp.headers else ""
            if "json" in ct or "text" in ct:
                try:
                    res_body = resp.text[:10000] if resp.text else None
                except Exception:
                    pass
            from services.logger import save_log
            asyncio.create_task(save_log(
                method=method,
                path=url,
                status_code=resp.status_code,
                duration_ms=duration,
                client_ip="Backend[Go-TLS]",
                headers={},
                request_body=req_body,
                response_body=res_body,
                error_detail=None if (200 <= resp.status_code < 400) else f"Status {resp.status_code}",
                account_id=self._account_id,
            ))
        except Exception:
            pass


def _create_go_tls_session(proxy_url: str | None, timeout: float) -> CurlAsyncSession:
    """创建匹配 Go 1.27 crypto/tls 指纹的 curl_cffi session
    
    使用自定义 JA3 + Akamai H2 指纹精确匹配 language_server binary 的 TLS 行为
    """
    from utils.fingerprint import GO_TLS_JA3, GO_H2_AKAMAI

    try:
        session = CurlAsyncSession(
            ja3=GO_TLS_JA3,
            akamai=GO_H2_AKAMAI,
            extra_fp={
                # curl_cffi 0.14.0 支持的参数:
                # tls_min_version, tls_grease, tls_permute_extensions,
                # tls_cert_compression, tls_signature_algorithms,
                # tls_delegated_credential, tls_record_size_limit,
                # http2_stream_weight, http2_stream_exclusive, http2_no_priority
                #
                # ❌ 不支持: tls_max_version (会报错)

                "tls_grease": False,               # Go 不使用 GREASE
                "tls_permute_extensions": False,     # Go 不随机排列扩展
                "tls_cert_compression": "brotli",    # Go 支持 brotli cert compression
                "http2_stream_weight": 256,          # Go default
                "http2_stream_exclusive": 1,         # Go default
            },
            proxy=proxy_url,
            timeout=timeout,
            http_version=2,
        )
        logger.info("Created Go TLS fingerprint session (custom JA3)")
        return session
    except Exception as e:
        # Fallback to Chrome impersonation if custom JA3 fails
        logger.warning(f"Custom JA3 failed ({e}), falling back to Chrome impersonation")
        return CurlAsyncSession(
            impersonate="chrome",
            proxy=proxy_url,
            timeout=timeout,
            http_version=2,
        )


def create_chrome_client(
    timeout: float = 30.0,
    account_id: str | None = None,
) -> "_ChromeSession":
    """Create a Go TLS client without context manager.

    Use this for streaming responses where the generator needs to own the
    session lifecycle. Caller MUST call client.close() when done.
    """
    proxy_url = _resolve_proxy()
    session = _create_go_tls_session(proxy_url, timeout)
    return _ChromeSession(session, account_id=account_id)


@asynccontextmanager
async def get_chrome_client(
    timeout: float = 30.0,
    account_id: str | None = None,
) -> AsyncIterator["_ChromeSession"]:
    """HTTP client with Go TLS fingerprint for Antigravity request impersonation.

    使用 curl_cffi 自定义 JA3 精确匹配 Go 1.27 crypto/tls 指纹:
      - TLS ClientHello cipher suites: AES_GCM + CHACHA20 (无 CBC)
      - Elliptic Curves: X25519MLKEM768, X25519, P-256, P-384
      - Extensions: ECH, certificate compression, etc.
      - HTTP/2 SETTINGS: Go net/http2 默认值
      - 不使用 GREASE, 不随机排列扩展
    
    如果自定义 JA3 配置失败，自动 fallback 到 Chrome impersonation。
    """
    proxy_url = _resolve_proxy()
    session = _create_go_tls_session(proxy_url, timeout)
    try:
        yield _ChromeSession(session, account_id=account_id)
    finally:
        await session.close()


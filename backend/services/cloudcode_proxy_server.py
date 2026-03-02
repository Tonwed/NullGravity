"""
CloudCode Proxy - ASGI Application

Minimal FastAPI app that runs on a separate port (default 9090).
Supports two modes:
1. Transparent proxy — Antigravity LS connects via jetski.cloudCodeUrl
2. OpenAI-compatible API — CherryStudio etc. connect via /v1/models, /v1/chat/completions
"""

from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware


def create_proxy_app() -> FastAPI:
    app = FastAPI(title="NullGravity CloudCode Proxy", docs_url=None, redoc_url=None)

    # CORS for external clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Token auth middleware for /v1/* routes ---
    @app.middleware("http")
    async def token_auth_middleware(request: Request, call_next):
        path = request.url.path

        # Only require auth for /v1/* endpoints, skip OPTIONS for CORS preflight
        if path.startswith("/v1/") and request.method != "OPTIONS":
            # Support both OpenAI (Authorization: Bearer sk-xxx) and Anthropic (x-api-key: sk-xxx)
            token_str = ""
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_str = auth_header[7:]
            if not token_str:
                token_str = request.headers.get("x-api-key", "")

            if not token_str:
                return JSONResponse(
                    status_code=401,
                    content={"error": {"message": "Missing API key. Set Authorization: Bearer sk-xxx", "type": "authentication_error"}},
                )

            from routers.api_tokens import validate_api_token
            is_valid = await validate_api_token(token_str)
            if not is_valid:
                return JSONResponse(
                    status_code=401,
                    content={"error": {"message": "Invalid API key", "type": "authentication_error"}},
                )

        return await call_next(request)

    # --- OpenAI-compatible routes (/v1/*) ---
    from services.openai_compat import router as openai_router
    app.include_router(openai_router, prefix="/v1")

    # --- Transparent proxy catch-all (for Antigravity LS) ---
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def proxy_catchall(request: Request, path: str):
        # Skip paths already handled by OpenAI router
        if path.startswith("v1/"):
            return JSONResponse(status_code=404, content={"error": "Not found"})

        from .cloudcode_proxy import handle_streaming_proxy_request
        import logging
        _log = logging.getLogger("proxy_intercept")

        # Read request body
        body = await request.body()

        # Log intercepted Language Server request for debugging
        if body and "GenerateContent" in path or "generateContent" in path or "streamGenerate" in path:
            try:
                import json as _j
                body_str = body.decode("utf-8", errors="replace")
                _log.warning(f"[LS-INTERCEPT] Path: {path}")
                _log.warning(f"[LS-INTERCEPT] Headers: {dict(request.headers)}")
                _log.warning(f"[LS-INTERCEPT] Body ({len(body)} bytes): {body_str[:3000]}")
            except Exception:
                _log.warning(f"[LS-INTERCEPT] Path: {path}, Body: {len(body)} bytes (decode failed)")

        # Collect headers
        headers = dict(request.headers)

        # Forward with streaming support
        # Safely convert query_params to string
        query_str = str(request.query_params)
        
        status, resp_headers, resp_body = await handle_streaming_proxy_request(
            method=request.method,
            path=path,
            headers=headers,
            body=body if body else None,
            query_string=query_str,
        )

        # If resp_body is an async iterator, stream it; otherwise return as bytes
        if hasattr(resp_body, "__aiter__"):
            return StreamingResponse(
                content=resp_body,
                status_code=status,
                headers=resp_headers,
            )
        else:
            return Response(
                content=resp_body,
                status_code=status,
                headers=resp_headers,
            )

    return app

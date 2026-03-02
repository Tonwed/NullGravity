import time

import asyncio
from datetime import timezone
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.concurrency import iterate_in_threadpool

from database.connection import async_session
from models.log import Log
from utils.websocket import manager

import re

UUID_PATTERN = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

async def _save_log(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: str | None,
    headers: dict,
    request_body: str | None,
    response_body: str | None,
    error_detail: str | None,
    account_id: str | None = None
):
    try:
        # Redact headers
        h = headers.copy()
        # Lowercase keys for consistent redaction
        h_lower = {k.lower(): v for k, v in h.items()}
        if "authorization" in h_lower: h_lower["authorization"] = "[REDACTED]"
        if "cookie" in h_lower: h_lower["cookie"] = "[REDACTED]"

        async with async_session() as session:
            log_entry = Log(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_headers=h_lower,
                request_body=request_body[:5000] if request_body else None,
                response_body=response_body[:5000] if response_body else None,
                error_detail=error_detail,
                account_id=account_id
            )
            session.add(log_entry)
            await session.commit()
            
            # Refresh to get ID and relationships
            await session.refresh(log_entry, ["account"])
            
            # Broadcast to WebSocket
            msg = {
                "id": log_entry.id,
                "timestamp": log_entry.timestamp.replace(tzinfo=timezone.utc).isoformat() if log_entry.timestamp.tzinfo is None else log_entry.timestamp.isoformat(),
                "method": log_entry.method,
                "path": log_entry.path,
                "status_code": log_entry.status_code,
                "duration_ms": log_entry.duration_ms,
                "client_ip": log_entry.client_ip,
                "request_headers": log_entry.request_headers,
                "request_body": log_entry.request_body,
                "response_body": log_entry.response_body,
                "error_detail": log_entry.error_detail,
                "account": {
                    "id": log_entry.account.id,
                    "email": log_entry.account.email,
                    "avatar_url": log_entry.account.avatar_url,
                    "display_name": log_entry.account.display_name
                } if log_entry.account else None
            }
            await manager.broadcast({"type": "log", "payload": msg})
    except Exception as e:
        print(f"Failed to log request: {e}")

class RequestLogger(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Paths to ignore (health checks, docs, and logs API itself to avoid loops)
        if request.url.path.startswith(("/docs", "/openapi.json", "/favicon.ico", "/api/logs", "/api/health", "/api/ws")):
            return await call_next(request)

        start_time = time.time()
        
        # Extract account_id from path if present (heuristic)
        account_id = None
        match = UUID_PATTERN.search(request.url.path)
        if match:
            account_id = match.group(1)
        
        # Capture request body
        req_body_str = None
        try:
            req_body = await request.body()
            if req_body:
                req_body_str = req_body.decode('utf-8', errors='replace')
                # Important: reset stream so downstream can read it
                async def receive():
                    return {"type": "http.request", "body": req_body, "more_body": False}
                request._receive = receive
        except Exception:
            pass

        try:
            response = await call_next(request)
        except Exception as e:
            # Log error if unhandled exception occurs
            process_time = (time.time() - start_time) * 1000
            asyncio.create_task(_save_log(
                method=request.method,
                path=str(request.url),
                status_code=500,
                duration_ms=process_time,
                client_ip=request.client.host if request.client else None,
                headers=dict(request.headers),
                request_body=req_body_str,
                response_body=None,
                error_detail=str(e),
                account_id=account_id
            ))
            raise e

        process_time = (time.time() - start_time) * 1000

        # Capture response body for non-streaming content
        res_body_str = None
        content_type = response.headers.get("content-type", "")
        is_stream = "text/event-stream" in content_type or "application/octet-stream" in content_type
        
        if not is_stream and hasattr(response, "body_iterator"):
            # Consume body iterator
            try:
                res_chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(res_chunks))
                res_body = b"".join(res_chunks)
                res_body_str = res_body.decode('utf-8', errors='replace')
            except Exception:
                res_body_str = "[Binary Response or Error]"
        
        # Save log in background
        asyncio.create_task(_save_log(
            method=request.method,
            path=str(request.url),
            status_code=response.status_code,
            duration_ms=process_time,
            client_ip=request.client.host if request.client else None,
            headers=dict(request.headers),
            request_body=req_body_str,
            response_body=res_body_str,
            error_detail=None,
            account_id=account_id
        ))
        
        return response

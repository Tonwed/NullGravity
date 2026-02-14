from datetime import timezone

from database.connection import async_session
from models.log import Log
from utils.websocket import manager

async def save_log(
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
            await session.refresh(log_entry, ["account"])
            
            # Broadcast to WebSocket
            ts = log_entry.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            msg = {
                "id": log_entry.id,
                "timestamp": ts.isoformat(),
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
        print(f"Failed to save log: {e}")


"""API routes for request logs."""

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc, func, delete
from sqlalchemy.orm import selectinload
from utils.websocket import manager
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_session
from models.log import Log
from schemas.log import LogListResponse, LogEntry

router = APIRouter()

@router.get("/", response_model=LogListResponse)
async def list_logs(
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    session: AsyncSession = Depends(get_session)
):
    """List logs with pagination and search."""
    query = select(Log).options(selectinload(Log.account)).order_by(desc(Log.timestamp))
    count_query = select(func.count(Log.id))

    if search:
        # Search in path or method or status code (if numeric search)
        condition = Log.path.icontains(search) | Log.method.icontains(search)
        if search.isdigit():
             condition = condition | (Log.status_code == int(search))
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = (await session.execute(count_query)).scalar() or 0
    
    # Calculate offset
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await session.execute(query)
    logs = result.scalars().all()

    return LogListResponse(
        items=[LogEntry.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size
    )

@router.delete("/")
async def clear_logs(session: AsyncSession = Depends(get_session)):
    """Clear all logs."""
    await session.execute(delete(Log))
    await session.commit()
    await session.commit()
    return {"success": True}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

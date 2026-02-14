"""
NullGravity Backend - FastAPI Application
AI Account Management & Protocol Proxy System
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.connection import init_db, close_db, async_session
from routers import accounts, settings, auth, logs, dashboard
from models.log import Log
from models.event import Event
from utils.proxy import load_proxy_from_db, start_proxy_monitor
from services.auto_refresh import start_auto_refresh_scheduler
from services.event import log_event
from utils.websocket import manager
from fastapi import WebSocket, WebSocketDisconnect
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    await init_db()
    
    # Load proxy setting into memory cache on startup
    async with async_session() as session:
        await load_proxy_from_db(session)
        # Log system startup event
        await log_event(session, "system.start", "Application backend started", level="info")
    
    # Start background tasks
    monitor_task = asyncio.create_task(start_proxy_monitor())
    refresh_task = asyncio.create_task(start_auto_refresh_scheduler())
    
    yield
    
    refresh_task.cancel()
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(
    title="NullGravity API",
    description="AI Account Management & Protocol Proxy System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:1420", "http://127.0.0.1:8046", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)



@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8046, reload=True)

"""FastAPI entrypoint.

Run from the repository root:
    uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.research import router as research_router
from backend.app.api.routes import router
from backend.app.core.config import settings
from backend.app.services.runtime import runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.bootstrap_db()
    runtime.step(settings.tick_seconds)  # first snapshot before clients arrive
    runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description="Research/simulation prototype. Not connected to any real traffic controller.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(research_router)


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await runtime.ws.connect(ws)
    try:
        if runtime.snapshot:
            await ws.send_json({"type": "snapshot", **runtime.snapshot})
        while True:
            await ws.receive_text()  # keep-alive; client messages ignored for now
    except WebSocketDisconnect:
        pass
    finally:
        runtime.ws.disconnect(ws)

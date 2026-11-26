"""WebSocket fan-out. One slow client never blocks the others."""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        text = json.dumps(payload, separators=(",", ":"))

        async def _send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2.0)
            except Exception:
                self.disconnect(ws)

        await asyncio.gather(*(_send(ws) for ws in list(self._clients)))

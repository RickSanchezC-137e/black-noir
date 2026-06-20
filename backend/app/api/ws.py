"""WebSocket channels (CANON §3). /ws/chat streams tokens."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import claude

router = APIRouter()


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            message = data.get("message", "")
            if not message:
                await ws.send_json({"type": "error", "data": "empty message"})
                continue
            try:
                async for tok in claude.stream(message):
                    await ws.send_json({"type": "token", "data": tok})
                await ws.send_json({"type": "done", "data": ""})
            except Exception as e:  # noqa: BLE001
                await ws.send_json({"type": "error", "data": str(e)})
    except WebSocketDisconnect:
        return


@router.websocket("/ws/activity")
async def ws_activity(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_json({"type": "hello", "data": "activity stream"})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        return

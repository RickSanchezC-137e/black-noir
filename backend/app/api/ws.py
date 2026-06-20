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


async def _hold(ws: WebSocket, name: str):
    await ws.accept()
    try:
        await ws.send_json({"type": "hello", "data": name})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        return


@router.websocket("/ws/activity")
async def ws_activity(ws: WebSocket):
    await _hold(ws, "activity stream")


@router.websocket("/ws/ideas")
async def ws_ideas(ws: WebSocket):
    await _hold(ws, "ideas stream")


@router.websocket("/ws/notify")
async def ws_notify(ws: WebSocket):
    await _hold(ws, "notify stream")


@router.websocket("/ws/tasks")
async def ws_tasks(ws: WebSocket):
    await _hold(ws, "tasks stream")


@router.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await _hold(ws, "logs stream")

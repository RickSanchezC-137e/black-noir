"""mcp_voice — perception-hearing (C3): real Piper TTS + faster-whisper STT (no stub).

Local on CPU (no GPU on VPS-01). Models lazy-loaded on first use. Voice IS NOT core
(CANON §5) — it is an organ the core orchestrates via this module.
"""
from __future__ import annotations

import os
import wave
from pathlib import Path

SANDBOX = Path(os.environ.get("NOIR_VOICE_SANDBOX", "/home/jarvis/noir/backend/data/voice")).resolve()
VOICE_ONNX = os.environ.get("NOIR_PIPER_VOICE",
                            "/home/jarvis/noir/secrets/voices/ru_RU-dmitri-medium.onnx")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

_piper = None
_whisper = None


def _safe(rel: str) -> Path:
    p = (SANDBOX / rel).resolve()
    if not (p == SANDBOX or SANDBOX in p.parents):
        raise ValueError("path escapes voice sandbox")
    return p


def _piper_voice():
    global _piper
    if _piper is None:
        from piper import PiperVoice
        _piper = PiperVoice.load(VOICE_ONNX)
    return _piper


def _whisper_model():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper


async def call(tool: str, args: dict) -> dict:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    if tool == "voice.speak":
        out = _safe(args.get("out", "tts_out.wav"))
        with wave.open(str(out), "wb") as wf:
            _piper_voice().synthesize_wav(args["text"], wf)
        return {"out": str(out.relative_to(SANDBOX)), "bytes": out.stat().st_size}
    if tool == "voice.transcribe":
        path = _safe(args["path"])
        segments, info = _whisper_model().transcribe(str(path), language=args.get("language", "ru"))
        text = "".join(s.text for s in segments).strip()
        return {"text": text, "language": info.language, "duration": round(info.duration, 2)}
    raise ValueError(f"unknown tool {tool}")


async def health() -> dict:
    return {"ok": Path(VOICE_ONNX).exists(), "voice": Path(VOICE_ONNX).name,
            "whisper": WHISPER_MODEL, "device": "cpu"}

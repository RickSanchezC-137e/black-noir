"""Hardware profiler (Rule 7 / build plan §4). Detects hardware at startup and
selects the local-layer level. No assumptions that a GPU exists.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass
class GPU:
    present: bool
    vram_mb: int = 0
    name: str = ""


@dataclass
class HardwareProfile:
    cpu_cores: int
    ram_mb: int
    gpu: GPU
    local_layer: str            # human-readable profile tier
    whisper_model: str
    whisper_device: str
    reflex: str                 # where the Reflex model runs


def _ram_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


def _gpu() -> GPU:
    if not shutil.which("nvidia-smi"):
        return GPU(present=False)
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            name, vram = out.stdout.strip().splitlines()[0].split(",")
            return GPU(present=True, vram_mb=int(vram), name=name.strip())
    except (subprocess.SubprocessError, ValueError):
        pass
    return GPU(present=False)


def detect_hardware() -> HardwareProfile:
    cpu = os.cpu_count() or 1
    ram = _ram_mb()
    gpu = _gpu()

    # Local-layer selection (build plan §4 table)
    if gpu.present and gpu.vram_mb >= 16000:
        tier, whisper, dev, reflex = "gpu-16gb: local 7-14B reflex", "small", "cuda", "local-llm"
    elif gpu.present and gpu.vram_mb >= 8000:
        tier, whisper, dev, reflex = "gpu-8gb: local 7B quantized", "small", "cuda", "local-llm"
    elif not gpu.present and ram >= 16000:
        tier, whisper, dev, reflex = "cpu-16gb: small CPU models, heavy via Claude API", "base", "cpu", "claude-api"
    else:
        tier, whisper, dev, reflex = "weak: cloud-only (Claude API), local embeddings only", "base", "cpu", "claude-api"

    return HardwareProfile(
        cpu_cores=cpu, ram_mb=ram, gpu=gpu,
        local_layer=tier, whisper_model=whisper, whisper_device=dev, reflex=reflex,
    )


def profile_dict() -> dict:
    p = detect_hardware()
    d = asdict(p)
    return d

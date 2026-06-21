"""Adoption catalog — owner-supplied repo list mapped to 11_adoption.md verdicts.

`clone=True` => run the real pipeline (clone -> license+security scan -> wrap -> Eval).
`clone=False` => record the blueprint verdict directly (platforms/GPU/money/out-of-v1) to
respect CANON §13 ("не тащить произвольные зависимости") and save night budget.
"""
from __future__ import annotations

from app.core import adoption
from app.core.integrators import glances_integrator

# repo, capability, cluster, blueprint_verdict, clone, integrator, note
CATALOG = [
    # --- List 1 high ---
    ("chopratejas/headroom", "context compression (token savings)", "C2", "adopt", True, None, "lib; fidelity by judge"),
    ("jamiepine/voicebox", "TTS 7 engines / voice clone", "C1", "defer", False, None, "heavy w/o GPU; Piper fallback"),
    ("Panniantong/Agent-Reach", "social/content access (feeds Scout)", "C6", "adopt", True, None, "ToS/fragile; sandbox+Governor"),
    ("google-research/timesfm", "time-series forecast", "C4", "defer", False, None, "trading/income (out of v1), GPU"),
    ("nicolargo/glances", "live host metrics", "C6", "adopt", True, glances_integrator, "ADOPTED -> mcp_glances"),
    ("duplicati/duplicati", "encrypted scheduled backups", "C5", "adopt", False, None, ".NET app; run as isolated service"),
    ("actualbudget/actual", "local finance ledger", "C2", "improve", False, None, "v1: model/analytics only"),
    ("paperless-ngx/paperless-ngx", "document OCR + search", "C3", "improve", False, None, "full stack pulls PG+Redis; use OCRmyPDF+Tesseract engine"),
    # --- List 1 medium ---
    ("DeusData/codebase-memory-mcp", "code knowledge graph", "C4", "adopt", True, None, "already MCP; aids self-modify"),
    ("NVIDIA/SkillSpector", "AI-module security scanner", "C5", "adopt", True, None, "becomes the adoption security-scan step"),
    ("n0-computer/iroh", "P2P device link", "C1", "defer", False, None, "for wearable/multi-device later"),
    ("docker-mailserver/docker-mailserver", "mail server", "C1", "defer", False, None, "optional email I/O"),
    ("NickVisionApps/Parabolic", "video/audio download (yt-dlp GUI)", "C3", "defer", False, None, "prefer yt-dlp directly"),
    ("qarmin/czkawka", "duplicate finder", "C2", "defer", False, None, "self-improve task, not v1"),
    ("mifi/lossless-cut", "video cut/join", "C3", "skip", False, None, "desktop GUI, not a server module"),
    ("asciinema/asciinema", "terminal session record", "C5", "defer", False, None, "optional Builder/CC audit"),
    # --- List 1 future (GPU) ---
    ("LMCache/LMCache", "KV cache for local LLM", "C4", "defer", False, None, "needs GPU"),
    ("QwenLM/Qwen3", "open LLM (local core candidate)", "C4", "defer", False, None, "v1 brain stays Claude; provider abstraction"),
    # --- List 2 high ---
    ("TauricResearch/TradingAgents", "multi-agent trading", "C4", "defer", False, None, "money/out of v1"),
    ("browser-use/browser-use", "real browser for AI", "C6", "adopt", True, None, "augments Playwright; LLM-loop cost -> sandbox+Governor"),
    ("langflow-ai/langflow", "visual agent flows", "C4", "skip", False, None, "platform/own stack — REFERENCE only, not core"),
    ("langgenius/dify", "AI platform", "C4", "skip", False, None, "platform/own stack — REFERENCE only, not core"),
    ("yt-dlp/yt-dlp", "video/audio downloader", "C3", "adopt", True, None, "lightweight canonical downloader"),
    ("ollama/ollama", "local LLM runtime", "C4", "defer", False, None, "provider abstraction; value needs GPU"),
    ("openai/whisper", "STT 99 languages", "C3", "defer", False, None, "faster-whisper default; whisper-large w/ GPU"),
    ("myshell-ai/OpenVoice", "voice clone (local)", "C1", "defer", False, None, "GPU-leaning; Piper fallback"),
    ("nickel11/FincceptTerminal", "market data terminal", "C2", "defer", False, None, "trading/income (out of v1)"),
    ("bitwarden/server", "self-host secret manager", "C5", "improve", False, None, "prefer lighter Vaultwarden (Rust)"),
    # --- List 2 medium ---
    ("n8n-io/n8n", "integration hub", "C6", "skip", False, None, "isolated service only, not orchestrator"),
    ("unclecode/crawl4ai", "LLM-oriented web crawl", "C6", "adopt", True, None, "page extraction for RAG/research"),
    ("open-webui/open-webui", "local-model chat UI", "C1", "defer", False, None, "dev/debug UI; our desktop is the product"),
    ("h2oai/wave", "python dashboards", "C4", "skip", False, None, "desktop covers it"),
    ("awesome-selfhosted/awesome-selfhosted", "self-hosted catalog", "C4", "defer", False, None, "reference for Scout"),
    ("webmin/webmin", "linux web admin", "C5", "defer", False, None, "Noir self-administers; manual fallback"),
    # --- List 2 future ---
    ("lllyasviel/Fooocus", "local image generation", "C3", "defer", False, None, "needs GPU"),
    ("penpot/penpot", "design tool", "-", "skip", False, None, "not relevant to core"),
    ("plausible/community-edition", "web analytics", "-", "skip", False, None, "not relevant to core"),
]


def by_repo(repo: str):
    return next((c for c in CATALOG if c[0] == repo), None)


def seed() -> int:
    """Record the blueprint verdict for every catalog repo not yet decided. Returns count seeded."""
    done = {a["repo"] for a in adoption.list_adoptions()}
    n = 0
    for repo, cap, cl, verdict, clone, integ, note in CATALOG:
        if repo in done:
            continue
        adoption._record({"repo": repo, "capability": cap, "cluster": cl,
                          "verdict": verdict, "reason": ("blueprint verdict; " + note),
                          "module_id": ""})
        n += 1
    return n


def _scanned(row) -> bool:
    # a real pipeline run leaves a reason that is NOT the seeded "blueprint verdict; ..."
    return bool(row) and not str(row.get("reason", "")).startswith("blueprint verdict")


def next_clone_candidate():
    """Next clone=True repo not yet scanned by the real pipeline (glances already integrated)."""
    rows = {a["repo"]: a for a in adoption.list_adoptions()}
    for repo, cap, cl, verdict, clone, integ, note in CATALOG:
        if not clone or repo == "nicolargo/glances":
            continue
        if not _scanned(rows.get(repo)):
            return (repo, cap, cl, integ)
    return None

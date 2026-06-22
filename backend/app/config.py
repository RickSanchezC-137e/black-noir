"""Noir core configuration (pydantic-settings).

Loads secrets/.env (prod) or backend/.env (dev). Fatal if ANTHROPIC_API_KEY missing
(INSTRUCTIONS §2). Project name is centralized in PROJECT_NAME (CANON §14) — never hardcode.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO = Path(__file__).resolve().parents[2]          # /home/jarvis/noir
_SECRETS_ENV = _REPO / "secrets" / ".env"
_DEV_ENV = _REPO / "backend" / ".env"
_ENV_FILE = _SECRETS_ENV if _SECRETS_ENV.exists() else _DEV_ENV


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore", case_sensitive=False)

    # Identity (rename-friendly — single source)
    project_name: str = "Black Noir"

    # LLM
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-8"
    claude_code_bin: str = "claude"
    llm_max_tokens: int = 4096

    # Council of models (multi-LLM core). Missing key → that member is skipped.
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    xai_api_key: str = ""
    xai_model: str = "grok-2-latest"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    council_timeout_s: float = 30.0

    # Search / integrations
    tavily_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_owner_chat_id: str = ""
    telegram_allowed_user_ids: str = ""
    telegram_notify_secret: str = ""
    github_token: str = ""

    # Network
    public_domain: str = "jarvisgod.duckdns.org"
    duckdns_token: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = ""

    # Data paths
    data_dir: Path = _REPO / "backend" / "data"
    sqlite_path: Path = _REPO / "backend" / "data" / "noir.sqlite"
    chroma_dir: Path = _REPO / "backend" / "data" / "chroma"
    voices_dir: Path = _REPO / "secrets" / "voices"

    # Memory / embeddings (CANON: all-MiniLM-L6-v2, dim=384)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Voice
    whisper_model: str = "base"
    whisper_device: str = "auto"
    piper_voice: str = "ru_RU-dmitri-medium.onnx"

    # Self-improvement night budget (09_self_improvement.md §9)
    selfimprove_daily_budget_tokens: int = 1_500_000
    selfimprove_daily_budget_requests: int = 300
    selfimprove_max_builder_runs: int = 20
    selfimprove_max_adopt_clones: int = 8
    selfimprove_night_enabled: int = 1

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()


def validate_or_die() -> None:
    """Fatal start guard (INSTRUCTIONS §2)."""
    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("<<"):
        sys.stderr.write("FATAL: ANTHROPIC_API_KEY missing in secrets/.env\n")
        raise SystemExit(2)
    settings.ensure_dirs()

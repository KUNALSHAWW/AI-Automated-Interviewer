"""Runtime configuration. Everything comes from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_URLS = {
    "ollama": "https://ollama.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

# Model ids verified against the providers' public listings on 2026-10-10:
#   ollama.com/api/tags, openrouter.ai/api/v1/models, console.groq.com/docs/models
DEFAULT_LIVE_CHAIN = "groq:openai/gpt-oss-20b,ollama:gemma4:31b,openrouter:google/gemma-4-31b-it:free"
DEFAULT_VISION_CHAIN = "ollama:gemma4:31b,openrouter:google/gemma-4-31b-it:free,ollama:kimi-k2.6"
DEFAULT_COUNCIL_CHAIN = (
    "ollama:gpt-oss:120b,ollama:gemma4:31b,groq:openai/gpt-oss-120b,"
    "ollama:glm-5.3-flash,openrouter:google/gemma-4-31b-it:free"
)
DEFAULT_STT_CHAIN = "groq:whisper-large-v3-turbo,openrouter:openai/whisper-large-v3-turbo"


def parse_chain(raw: str) -> list[tuple[str, str]]:
    """'groq:openai/gpt-oss-20b,ollama:gemma4:31b' -> [('groq','openai/gpt-oss-20b'), ('ollama','gemma4:31b')]"""
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        provider, _, model = part.partition(":")
        if not model:
            raise ValueError(f"Bad chain entry {part!r}: expected provider:model")
        out.append((provider.strip().lower(), model.strip()))
    return out


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- credentials -------------------------------------------------------
    ollama_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    github_token: str = ""
    ollama_base_url: str = BASE_URLS["ollama"]

    # --- provider chains (first available wins, the rest are fallbacks) ----
    live_chain: list = field(default_factory=lambda: parse_chain(DEFAULT_LIVE_CHAIN))
    vision_chain: list = field(default_factory=lambda: parse_chain(DEFAULT_VISION_CHAIN))
    council_chain: list = field(default_factory=lambda: parse_chain(DEFAULT_COUNCIL_CHAIN))
    stt_chain: list = field(default_factory=lambda: parse_chain(DEFAULT_STT_CHAIN))
    council_size: int = 3

    # --- storage / access --------------------------------------------------
    data_dir: Path = Path("data")
    retention_days: int = 30
    access_code: str = ""
    cors_origins: tuple = ("http://localhost:3000", "http://127.0.0.1:3000")
    frontend_dist: Path = Path("../frontend/dist")
    max_concurrent_sessions: int = 2  # each live session can have 2 requests in flight; Ollama Pro allows 3
    sessions_per_hour_per_ip: int = 12
    trust_proxy: bool = False      # honour X-Forwarded-For (set on Render)
    max_session_minutes: int = 30

    # --- turn taking -------------------------------------------------------
    pause_s: float = 2.5           # silence after the last utterance before the AI may speak
    min_ai_gap_s: float = 20.0     # minimum seconds between two AI questions
    min_words_to_ask: int = 35     # do not interrupt before the presenter said this much
    max_words_without_ai: int = 160  # ask anyway after this many words
    reshare_timeout_s: float = 30.0

    # --- vision ------------------------------------------------------------
    tile_threshold: float = 0.03   # per-tile mean difference (0-1) that counts as "changed"
    min_changed_tiles: int = 3     # of 144 tiles
    vision_min_interval_s: float = 4.0

    # --- cost estimate -----------------------------------------------------
    stt_price_per_hour: float = 0.04  # whisper-large-v3-turbo on Groq (console.groq.com/docs/speech-to-text)

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip())
        return cls(
            ollama_api_key=_env("OLLAMA_API_KEY"),
            groq_api_key=_env("GROQ_API_KEY"),
            openrouter_api_key=_env("OPENROUTER_API_KEY"),
            github_token=_env("GITHUB_TOKEN"),
            ollama_base_url=_env("OLLAMA_BASE_URL", BASE_URLS["ollama"]).rstrip("/"),
            live_chain=parse_chain(_env("LIVE_CHAIN", DEFAULT_LIVE_CHAIN)),
            vision_chain=parse_chain(_env("VISION_CHAIN", DEFAULT_VISION_CHAIN)),
            council_chain=parse_chain(_env("COUNCIL_CHAIN", DEFAULT_COUNCIL_CHAIN)),
            stt_chain=parse_chain(_env("STT_CHAIN", DEFAULT_STT_CHAIN)),
            council_size=max(1, _int("COUNCIL_SIZE", 3)),
            data_dir=Path(_env("DATA_DIR", "data")),
            retention_days=_int("RETENTION_DAYS", 30),
            access_code=_env("ACCESS_CODE"),
            cors_origins=origins,
            frontend_dist=Path(_env("FRONTEND_DIST", "../frontend/dist")),
            max_concurrent_sessions=_int("MAX_CONCURRENT_SESSIONS", 2),
            sessions_per_hour_per_ip=_int("SESSIONS_PER_HOUR_PER_IP", 12),
            trust_proxy=_env("TRUST_PROXY", "0").lower() in {"1", "true", "yes"},
            max_session_minutes=_int("MAX_SESSION_MINUTES", 30),
            pause_s=_float("PAUSE_SECONDS", 2.5),
            min_ai_gap_s=_float("MIN_AI_GAP_SECONDS", 20.0),
            min_words_to_ask=_int("MIN_WORDS_TO_ASK", 35),
            max_words_without_ai=_int("MAX_WORDS_WITHOUT_AI", 160),
            reshare_timeout_s=_float("RESHARE_TIMEOUT_SECONDS", 30.0),
            tile_threshold=_float("VISION_TILE_THRESHOLD", 0.03),
            min_changed_tiles=_int("VISION_MIN_CHANGED_TILES", 3),
            vision_min_interval_s=_float("VISION_MIN_INTERVAL_SECONDS", 4.0),
            stt_price_per_hour=_float("STT_PRICE_PER_HOUR", 0.04),
        )

    # --- helpers -----------------------------------------------------------
    def base_url(self, provider: str) -> str:
        return self.ollama_base_url if provider == "ollama" else BASE_URLS[provider]

    def api_key(self, provider: str) -> str:
        return {
            "ollama": self.ollama_api_key,
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
        }.get(provider, "")

    def provider_ready(self, provider: str) -> bool:
        if provider not in BASE_URLS:
            return False
        if provider == "ollama" and any(h in self.ollama_base_url for h in ("localhost", "127.0.0.1")):
            return True  # a local Ollama server needs no key
        return bool(self.api_key(provider))

    def chain_available(self, chain: list) -> list:
        return [(p, m) for p, m in chain if self.provider_ready(p)]

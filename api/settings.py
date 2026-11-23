"""App settings, read from environment / api/.env (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # Prefix: PM2 injects its own config keys (env, name, args, ...) as env vars; never read those.
    model_config = SettingsConfigDict(env_prefix="AIWAZZ_", env_file=API_DIR / ".env",
                                      env_file_encoding="utf-8", extra="ignore")

    env: str = "production"
    host: str = "127.0.0.1"
    port: int = 8100

    storage_dir: Path = API_DIR / "storage"
    audio_retention_days: int = Field(7, ge=1)

    # TTS
    torch_threads: int = Field(4, ge=1, le=16)
    max_chars: int = Field(5000, ge=1)
    max_queue: int = Field(20, ge=1)          # jobs waiting + running; beyond this → 429
    sentence_pause_ms: int = 250
    paragraph_pause_ms: int = 600

    # Post-processing
    sample_rate: int = 48000
    mp3_bitrate: str = "192k"
    edge_silence_ms: int = 100                # silence kept at start/end after trimming
    silence_threshold_db: float = -45.0       # below this (dBFS RMS) counts as silence
    loudness_lufs: float = Field(-14.0, ge=-30.0, le=-8.0)
    true_peak_db: float = Field(-1.0, ge=-9.0, le=0.0)
    compressor: bool = True                   # gentle 2:1 compressor before gain/limiter
    compressor_threshold_rel_db: float = 0.0  # relative to the clip's measured loudness
    compressor_ratio: float = Field(2.0, ge=1.0, le=8.0)

    # Database / Redis (secrets live in .env only)
    database_url: str = ""                    # mysql+aiomysql://user:pw@127.0.0.1:3306/aiwazz_voice?charset=utf8mb4
    redis_url: str = "redis://127.0.0.1:6379/5"
    redis_prefix: str = "aiwazz:"

    # Auth
    allowed_origins: list[str] = ["https://login.aiwazz.in"]  # Origin check for cookie-authenticated writes
    cookie_secure: bool = True                # False only for local http dev (drops the __Host- prefix)
    session_days: int = Field(30, ge=1, le=365)
    login_max_per_email: int = 5              # per 15 minutes
    login_max_per_ip: int = 20                # per 15 minutes
    signup_max_per_ip: int = 10               # per hour
    password_min_length: int = Field(10, ge=8)

    @property
    def session_cookie(self) -> str:
        return "__Host-aiwazz_session" if self.cookie_secure else "aiwazz_session"

    @property
    def csrf_cookie(self) -> str:
        return "__Host-aiwazz_csrf" if self.cookie_secure else "aiwazz_csrf"

    @property
    def debug(self) -> bool:
        """Fail-closed: API docs etc. only for an explicit dev/test env."""
        return self.env in ("development", "test")

    @property
    def audio_dir(self) -> Path:
        return self.storage_dir / "audio"


@lru_cache
def get_settings() -> Settings:
    return Settings()

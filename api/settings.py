"""App settings, read from environment / api/.env (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

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

    @property
    def audio_dir(self) -> Path:
        return self.storage_dir / "audio"


@lru_cache
def get_settings() -> Settings:
    return Settings()

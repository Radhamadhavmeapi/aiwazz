"""Client for the voice-clone worker (voiceclone/worker.py). Blocking; called from the clone queue's thread."""
import io

import httpx
import numpy as np
import soundfile as sf


class CloneError(Exception):
    """The worker could not convert (down, overloaded, bad answer). The job retries once, then fails uncharged."""


class CloneClient:
    def __init__(self, url: str, secret: str, timeout: float):
        self.url = url.rstrip("/")
        self.secret = secret
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def _headers(self) -> dict:
        return {"X-Clone-Secret": self.secret}

    def health(self) -> dict:
        try:
            r = httpx.get(f"{self.url}/health", headers=self._headers(), timeout=5)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise CloneError(f"worker unreachable: {type(e).__name__}") from e

    def convert(self, audio: np.ndarray, sr: int, voice_id: str) -> tuple[np.ndarray, int]:
        buf = io.BytesIO()
        sf.write(buf, audio.astype(np.float32), sr, format="WAV", subtype="FLOAT")
        try:
            r = httpx.post(f"{self.url}/convert", params={"voice_id": voice_id}, content=buf.getvalue(),
                           headers=self._headers() | {"Content-Type": "audio/wav"}, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise CloneError(f"worker unreachable: {type(e).__name__}") from e
        if r.status_code != 200:
            raise CloneError(f"worker answered {r.status_code}")
        out, out_sr = sf.read(io.BytesIO(r.content), dtype="float32", always_2d=False)
        return out, out_sr

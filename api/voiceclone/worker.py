"""voice-clone worker (phase 13): its own PM2 process on 127.0.0.1, so a crash or memory spike never takes Kokoro down.

    POST /convert?voice_id=<id>   body: WAV (mono, any rate) of Kokoro speech for one sentence
                                  → WAV (float32, 22.05 kHz) in the clone voice
    GET  /health                  {"status", "voices": [ready ids]}

Every call needs `X-Clone-Secret` (AIWAZZ_CLONE_SECRET in api/.env). One conversion at a time (lock), torch threads
capped (AIWAZZ_CLONE_THREADS), started under `nice -n 10` by PM2. The tone colours are precomputed by
`python -m voiceclone.prepare` and only read here. A GPU worker later implements the same interface: change
AIWAZZ_CLONE_URL.
Run: .venv/bin/uvicorn voiceclone.worker:app --host 127.0.0.1 --port 8101
"""
import hashlib
import hmac
import io
import logging
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from settings import get_settings
from tts.clone_voices import CloneVoice, load_clone_voices

log = logging.getLogger("voiceclone")
MODEL_NAME = "openvoice_v2"
MAX_BODY = 20 * 1024 * 1024        # one sentence of 24 kHz float audio is far below this
MIN_FREE_MB = 400                  # refuse work instead of pushing the server towards swap


def mem_available_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 1 << 30


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tone_color_path(voice: CloneVoice):
    return get_settings().data_dir / "voices" / voice.id / "tone_color.pt"


def load_tone_color(voice: CloneVoice) -> dict | None:
    """Cached tone colours, valid only for this model + this exact reference file + source voice."""
    import torch
    p = tone_color_path(voice)
    if not p.is_file():
        return None
    tc = torch.load(p, map_location="cpu", weights_only=True)
    ref = get_settings().data_dir / "voices" / voice.id / voice.reference_path
    if (tc.get("model") != MODEL_NAME or tc.get("source_voice") != voice.source_voice
            or not ref.is_file() or tc.get("reference_sha256") != file_sha256(ref)):
        log.warning("tone colour for %s is stale: run python -m voiceclone.prepare --voice %s", voice.id, voice.id)
        return None
    return tc


class State:
    def __init__(self):
        self.converter = None
        self.voices: dict[str, CloneVoice] = {}
        self.tones: dict[str, dict] = {}
        self.lock = threading.Lock()

    def load(self) -> None:
        import torch
        s = get_settings()
        torch.set_num_threads(s.clone_threads)
        torch.backends.nnpack.set_flags(False)   # this CPU has no NNPACK support; avoids a warning per call
        from .converter import ToneConverter
        self.converter = ToneConverter(s.data_dir / "models" / MODEL_NAME)
        log.info("converter loaded in %.1fs (%d threads)", self.converter.load(), torch.get_num_threads())
        self.voices = load_clone_voices(s.data_dir / "voices")
        for vid, v in self.voices.items():
            tc = load_tone_color(v)
            if tc is not None:
                self.tones[vid] = tc
        log.info("clone voices ready: %s", ", ".join(self.tones) or "none")


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not get_settings().clone_secret:
        raise RuntimeError("AIWAZZ_CLONE_SECRET is not set (api/.env); refusing to start")
    await run_in_threadpool(state.load)
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def check_secret(secret: str | None) -> None:
    expected = get_settings().clone_secret
    if not expected or not secret or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(401, "bad secret")


@app.get("/health")
async def health(x_clone_secret: str | None = Header(None)):
    check_secret(x_clone_secret)
    return {"status": "ok" if state.converter else "loading", "voices": sorted(state.tones),
            "model": MODEL_NAME, "busy": state.lock.locked()}


def _convert(voice_id: str, data: bytes) -> tuple[bytes, dict]:
    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size < sr // 20:                     # < 50 ms: nothing to convert; answer silence at the output rate
        out_sr = state.converter.sample_rate
        out, stats = np.zeros(out_sr // 100, dtype=np.float32), {"convert_sec": 0.0}
    else:
        tc, v = state.tones[voice_id], state.voices[voice_id]
        with state.lock:                          # one conversion at a time
            t0 = time.perf_counter()
            out = state.converter.convert(audio, sr, tc["src_se"], tc["tgt_se"], tau=v.tau)
            stats = {"convert_sec": round(time.perf_counter() - t0, 3)}
        out_sr = state.converter.sample_rate
        out = np.clip(out, -1.0, 1.0)
    buf = io.BytesIO()
    sf.write(buf, out, out_sr, format="WAV", subtype="FLOAT")
    return buf.getvalue(), stats


@app.post("/convert")
async def convert(request: Request, voice_id: str = Query(..., max_length=64),
                  x_clone_secret: str | None = Header(None)):
    check_secret(x_clone_secret)
    if voice_id not in state.tones:
        raise HTTPException(404, "voice not ready")
    if mem_available_mb() < MIN_FREE_MB:
        raise HTTPException(503, "low memory, try again")
    body = await request.body()
    if not body or len(body) > MAX_BODY:
        raise HTTPException(413, "bad audio size")
    try:
        out, stats = await run_in_threadpool(_convert, voice_id, body)
    except (RuntimeError, ValueError, sf.LibsndfileError) as e:
        log.exception("conversion failed")
        raise HTTPException(422, f"conversion failed: {type(e).__name__}")
    return Response(out, media_type="audio/wav", headers={"X-Convert-Sec": str(stats["convert_sec"])})

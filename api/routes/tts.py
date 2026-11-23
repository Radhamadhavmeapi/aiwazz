"""Public API routes (phase 2: no auth yet; the service binds to 127.0.0.1 only)."""
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from settings import get_settings
from tts.jobs import ID_RE, JobManager, QueueFull, TTSRequest
from tts.voices import DEFAULT_VOICE, VOICES

router = APIRouter(prefix="/api")
WAIT_TIMEOUT = 290  # stay under nginx proxy_read_timeout (300 s)


def manager(request: Request) -> JobManager:
    return request.app.state.jobs


class TTSIn(BaseModel):
    text: str = Field(min_length=1)
    engine: Literal["kokoro"] = "kokoro"
    voice: str = DEFAULT_VOICE
    lang: str | None = None                       # derived from the voice when omitted
    speed: float = Field(1.0, ge=0.7, le=1.3)
    format: Literal["mp3", "wav"] = "mp3"
    transliterate: bool = False
    normalize: bool = True                         # loudness normalisation on/off
    loudness_lufs: float | None = Field(None, ge=-30.0, le=-8.0)  # default from settings (-14)

    @model_validator(mode="after")
    def _check(self):
        s = get_settings()
        if not self.text.strip():
            raise ValueError("text is empty")
        if len(self.text) > s.max_chars:
            raise ValueError(f"text is longer than {s.max_chars} characters")
        v = VOICES.get(self.voice)
        if v is None or v.engine != self.engine:
            raise ValueError(f"unknown voice '{self.voice}' for engine '{self.engine}'")
        if self.lang is None:
            self.lang = v.lang
        elif self.lang != v.lang:
            raise ValueError(f"voice '{self.voice}' is language '{v.lang}', not '{self.lang}'")
        if self.transliterate:
            raise ValueError("transliterate is not available yet (phase 6)")
        return self


@router.get("/health")
async def health(request: Request):
    jm = manager(request)
    ready = jm.engine.ready
    body = {
        "status": "ok" if ready else "loading",
        "engines": {"kokoro": ready},
        "queue": {"running": jm.running is not None, "waiting": len(jm.pending)},
    }
    return JSONResponse(body, status_code=200 if ready else 503)


@router.get("/voices")
async def voices():
    return {"voices": [v.to_dict() for v in VOICES.values()]}


@router.post("/tts")
async def create_tts(body: TTSIn, request: Request,
                     wait: bool = Query(False, description="Block until done (≤290 s)")):
    jm = manager(request)
    if not jm.engine.ready:
        raise HTTPException(503, "TTS engine is still loading, try again in a few seconds")
    s = get_settings()
    req = TTSRequest(text=body.text, engine=body.engine, voice=body.voice, lang=body.lang,
                     speed=body.speed, format=body.format,
                     loudness_lufs=(body.loudness_lufs if body.loudness_lufs is not None else s.loudness_lufs)
                     if body.normalize else None)
    try:
        job = jm.submit(req)
    except QueueFull:
        raise HTTPException(429, "The queue is full, please try again in a minute")
    if wait:
        try:
            await asyncio.wait_for(job.done_event.wait(), WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            pass
    status = jm.status(job)
    if job.status == "error":
        return JSONResponse(status, status_code=422)
    return JSONResponse(status, status_code=200 if job.status == "done" else 202)


@router.get("/tts/jobs/{job_id}")
async def job_status(job_id: str, request: Request):
    jm = manager(request)
    job = jm.jobs.get(job_id) if ID_RE.match(job_id) else None
    if job is None:
        raise HTTPException(404, "Job not found")
    return jm.status(job)


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str, request: Request,
                    format: Literal["mp3", "wav"] = "mp3", download: bool = False):
    path = manager(request).audio_path(audio_id, format)
    if path is None:
        raise HTTPException(404, "Audio not found")
    media = "audio/mpeg" if format == "mp3" else "audio/wav"
    name = f"aiwazz-{audio_id[:8]}.{format}"
    return FileResponse(path, media_type=media, filename=name,
                        content_disposition_type="attachment" if download else "inline")

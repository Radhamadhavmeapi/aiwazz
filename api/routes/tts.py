"""TTS routes. Health + voices are public; everything else needs a session or an API key.
Audio is owner-only (admins can read everything)."""
import asyncio
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect, current_principal
from db import get_db, utcnow
from models import Generation
from usage import get_usage
from settings import get_settings
from tts.hinglish import latin_share, to_devanagari
from tts import pronounce
from tts.jobs import ID_RE, Job, JobManager, QueueFull, TooManyPending, TTSRequest
from tts.styles import STYLES
from tts.voices import DEFAULT_VOICE, VOICES

router = APIRouter(prefix="/api")
WAIT_TIMEOUT = 290  # stay under nginx proxy_read_timeout (300 s)


def manager(request: Request) -> JobManager:
    return request.app.state.jobs


def audio_urls(gen_id: str) -> dict:
    return {f: f"/api/audio/{gen_id}?format={f}" for f in ("mp3", "wav")}


class PronunciationIn(BaseModel):
    word: str = Field(min_length=1, max_length=pronounce.MAX_WORD)
    say_as: str = Field(min_length=1, max_length=pronounce.MAX_SAY_AS)

    @model_validator(mode="after")
    def _check(self):
        if msg := pronounce.check_entry(self.word, self.say_as):
            raise ValueError(msg)
        return self


class TTSIn(BaseModel):
    text: str = Field(min_length=1)
    engine: Literal["kokoro"] = "kokoro"
    voice: str = DEFAULT_VOICE
    lang: str | None = None                       # derived from the voice when omitted
    speed: float = Field(1.0, ge=0.7, le=1.3)
    format: Literal["mp3", "wav"] = "mp3"
    transliterate: bool = False
    normalize: bool = True                         # loudness normalisation on/off
    loudness_lufs: float | None = Field(None, ge=-30.0, le=-8.0)  # default: the style's, else settings (-14)
    style: str | None = None                       # tts/styles.py id: pace + pauses + loudness
    pronunciations: list[PronunciationIn] = Field(default_factory=list, max_length=pronounce.MAX_PER_REQUEST)

    @model_validator(mode="after")
    def _check(self):
        s = get_settings()
        if self.style is not None and self.style not in STYLES:
            raise ValueError(f"unknown style '{self.style}' (one of: {', '.join(STYLES)})")
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
        if self.transliterate and self.lang != "h":
            raise ValueError("transliterate works with Hindi voices only")
        return self


async def pronunciation_entries(db: AsyncSession, user_id: int, extra: list | None = None) -> list[pronounce.Entry]:
    """Request entries first, then the user's list, then the global list (first match wins)."""
    from models import Pronunciation
    rows = (await db.execute(select(Pronunciation).where((Pronunciation.user_id == user_id) | Pronunciation.user_id.is_(None))
                             .order_by(Pronunciation.user_id.is_(None), Pronunciation.id))).scalars().all()
    return [pronounce.Entry(e.word, e.say_as) for e in (extra or [])] + [pronounce.Entry(r.word, r.say_as) for r in rows]


def prepare_text(text: str, transliterate: bool, entries: list[pronounce.Entry]) -> str:
    """What the voice reads: inline [word](say-as) + dictionaries, then Hinglish → Devanagari on the rest."""
    return pronounce.render(pronounce.apply(text, entries), to_devanagari if transliterate else None)


class TranslitIn(BaseModel):
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _len(self):
        if len(self.text) > get_settings().max_chars:
            raise ValueError(f"text is longer than {get_settings().max_chars} characters")
        return self


@router.post("/transliterate", dependencies=[Depends(csrf_protect)])
async def transliterate(body: TranslitIn, p: Principal = Depends(current_principal)):
    """Preview of the Hinglish → Devanagari conversion used by `transliterate: true`."""
    return {"text": to_devanagari(body.text), "latin_share": round(latin_share(body.text), 3)}


class ReadAsIn(BaseModel):
    text: str = Field(min_length=1)
    transliterate: bool = False
    pronunciations: list[PronunciationIn] = Field(default_factory=list, max_length=pronounce.MAX_PER_REQUEST)

    @model_validator(mode="after")
    def _len(self):
        if len(self.text) > get_settings().max_chars:
            raise ValueError(f"text is longer than {get_settings().max_chars} characters")
        return self


@router.post("/read-as", dependencies=[Depends(csrf_protect)])
async def read_as(body: ReadAsIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    """Preview of what the voice will read: pronunciations (inline, request, yours, global) + optional transliteration."""
    out = prepare_text(body.text, body.transliterate, await pronunciation_entries(db, p.user.id, body.pronunciations))
    return {"text": out, "changed": out != body.text}


@router.get("/styles")
async def styles():
    return {"styles": [st.to_dict() for st in STYLES.values()]}


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


@router.post("/tts", dependencies=[Depends(csrf_protect)])
async def create_tts(
    body: TTSIn,
    request: Request,
    wait: bool = Query(False, description="Block until done (≤290 s)"),
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    jm = manager(request)
    if not jm.engine.ready:
        raise HTTPException(503, "TTS engine is still loading, try again in a few seconds")
    s = get_settings()
    style = STYLES.get(body.style) if body.style else None
    text = prepare_text(body.text, body.transliterate, await pronunciation_entries(db, p.user.id, body.pronunciations))
    if len(text) > 2 * s.max_chars:   # characters are counted on the original; don't let replacements blow it up
        raise HTTPException(422, "Pronunciation replacements make this script too long. Shorten the script or the replacements.")
    if body.loudness_lufs is not None:
        lufs = body.loudness_lufs
    else:
        lufs = style.loudness_lufs if style else s.loudness_lufs
    # A style sets the speed unless the request gives one explicitly.
    speed = style.speed if style and "speed" not in body.model_fields_set else body.speed
    req = TTSRequest(text=text, engine=body.engine, voice=body.voice, lang=body.lang, speed=speed, format=body.format,
                     loudness_lufs=lufs if body.normalize else None,
                     sentence_pause_ms=style.sentence_pause_ms if style else None,
                     paragraph_pause_ms=style.paragraph_pause_ms if style else None)
    try:
        jm.check_capacity(p.user.id)
    except QueueFull:
        raise HTTPException(429, "The queue is full, please try again in a minute")
    except TooManyPending:
        raise HTTPException(429, "You already have 3 voiceovers waiting. Let one finish first.")

    usage = await get_usage(db, p.user)
    if usage.remaining is not None and len(body.text) > usage.remaining:
        raise HTTPException(402, f"Not enough characters left this month: {usage.remaining:,} left, this script needs "
                                 f"{len(body.text):,}. Shorten the script, or upgrade your plan.")

    gen = Generation(
        id=secrets.token_hex(16), user_id=p.user.id, api_key_id=p.api_key.id if p.api_key else None,
        engine=req.engine, voice=req.voice, lang=req.lang, speed=req.speed, format=req.format,
        loudness_target=req.loudness_lufs, style=body.style, text_chars=len(body.text),
        text_excerpt=" ".join(pronounce.strip_inline(body.text).split())[:160],
    )
    db.add(gen)
    await db.commit()
    job = jm.submit(req, job_id=gen.id, user_id=p.user.id)

    if wait:
        try:
            await asyncio.wait_for(job.done_event.wait(), WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            pass
    status = jm.status(job)
    if job.status == "error":
        return JSONResponse(status, status_code=422)
    return JSONResponse(status, status_code=200 if job.status == "done" else 202)


async def _owned_generation(db: AsyncSession, gen_id: str, p: Principal) -> Generation:
    gen = await db.get(Generation, gen_id) if ID_RE.match(gen_id) else None
    # Same 404 for "doesn't exist" and "not yours": no probing other users' ids.
    if gen is None or (gen.user_id != p.user.id and not p.user.is_admin):
        raise HTTPException(404, "Not found")
    return gen


def _gen_status(gen: Generation) -> dict:
    d = {"id": gen.id, "status": gen.status, "progress": 1.0 if gen.status == "done" else 0.0}
    if gen.error:
        d["error"] = gen.error
    if gen.status == "done":
        d |= {"url": f"/api/audio/{gen.id}?format={gen.format}", "urls": audio_urls(gen.id),
              "duration_sec": gen.duration_sec, "compute_sec": gen.compute_sec}
    return d


@router.get("/tts/jobs/{job_id}")
async def job_status(job_id: str, request: Request, p: Principal = Depends(current_principal),
                     db: AsyncSession = Depends(get_db)):
    gen = await _owned_generation(db, job_id, p)
    jm = manager(request)
    job = jm.jobs.get(gen.id)
    return jm.status(job) if job else _gen_status(gen)  # in-memory has live progress; DB survives restarts


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str, request: Request, format: Literal["mp3", "wav"] = "mp3", download: bool = False,
                    p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    gen = await _owned_generation(db, audio_id, p)
    path = manager(request).audio_path(gen.id, format)
    if path is None:
        if gen.status == "done":
            raise HTTPException(410, "This audio has expired (files are kept for 7 days)")
        raise HTTPException(404, "Audio not ready")
    media = "audio/mpeg" if format == "mp3" else "audio/wav"
    return FileResponse(path, media_type=media, filename=f"aiwazz-{gen.id[:8]}.{format}",
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/history")
async def history(request: Request, limit: int = Query(50, ge=1, le=50), p: Principal = Depends(current_principal),
                  db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Generation).where(Generation.user_id == p.user.id)
                             .order_by(Generation.created_at.desc()).limit(limit))).scalars().all()
    jm = manager(request)
    items = []
    for g in rows:
        available = g.status == "done" and jm.audio_path(g.id, g.format) is not None
        items.append({
            "id": g.id, "status": g.status, "voice": g.voice, "lang": g.lang, "speed": g.speed, "format": g.format,
            "loudness_target": g.loudness_target, "style": g.style, "output_lufs": g.output_lufs, "text_excerpt": g.text_excerpt,
            "text_chars": g.text_chars, "duration_sec": g.duration_sec, "error": g.error, "via_api": g.api_key_id is not None,
            "created_at": g.created_at.isoformat() + "Z", "available": available,
            "urls": audio_urls(g.id) if available else None,
        })
    return {"items": items}


@router.get("/usage")
async def usage(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    """Plan, monthly character allowance and what's used (successful jobs only) / reserved (queued)."""
    return (await get_usage(db, p.user)).to_dict()


@router.delete("/history/{gen_id}", dependencies=[Depends(csrf_protect)])
async def delete_history_item(gen_id: str, request: Request, p: Principal = Depends(current_principal),
                              db: AsyncSession = Depends(get_db)):
    gen = await _owned_generation(db, gen_id, p)
    if gen.status in ("queued", "running"):
        raise HTTPException(409, "This voiceover is still being generated")
    for ext in ("mp3", "wav", "json"):
        (manager(request).s.audio_dir / f"{gen.id}.{ext}").unlink(missing_ok=True)
    await db.delete(gen)
    await db.commit()
    return {"ok": True}


# ── Job → DB hooks (wired in main.py) ─────────────────────────────────────────
def make_hooks(sessionmaker):
    async def on_start(job: Job) -> None:
        async with sessionmaker() as db:
            gen = await db.get(Generation, job.id)
            if gen:
                gen.status = "running"
                await db.commit()

    async def on_finish(job: Job) -> None:
        async with sessionmaker() as db:
            gen = await db.get(Generation, job.id)
            if not gen:
                return
            gen.status = job.status
            gen.finished_at = utcnow()
            if job.result:
                gen.duration_sec = job.result.get("duration_sec")
                gen.compute_sec = job.result.get("compute_sec")
                gen.output_lufs = (job.result.get("loudness") or {}).get("output_lufs")
            gen.error = (job.error or None) and job.error[:255]
            await db.commit()

    return on_start, on_finish

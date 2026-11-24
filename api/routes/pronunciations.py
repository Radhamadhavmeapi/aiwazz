"""Pronunciation dictionary: the user's own list, the global list (admins edit it) and a ▶ test.

GET    /api/pronunciations                 yours + global + built-in rules
POST   /api/pronunciations                 add or update (same word → updated)
DELETE /api/pronunciations/{id}
POST   /api/pronunciations/test            synthesize `say_as` with a voice → MP3 (not counted, 30/h)
POST   /api/admin/pronunciations           global list (admin, session only; moves to /admin in phase 12 A5)
DELETE /api/admin/pronunciations/{id}
"""
import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import ratelimit
from auth.deps import Principal, csrf_protect, current_principal
from db import get_db, utcnow
from models import Pronunciation
from settings import get_settings
from tts import pronounce
from tts.jobs import QueueFull, TooManyPending, TTSRequest
from tts.voices import DEFAULT_VOICE, VOICES

router = APIRouter(prefix="/api", tags=["pronunciations"])
BUILTIN = [{"word": "₹", "say_as": "रुपये (Hindi voices) / rupees (English voices)",
            "note": "Amounts too: ₹2,00,000 → दो लाख रुपये"}]
TEST_TIMEOUT = 60


def _out(r: Pronunciation) -> dict:
    return {"id": r.id, "word": r.word, "say_as": r.say_as, "updated_at": r.updated_at.isoformat() + "Z"}


class EntryIn(BaseModel):
    word: str = Field(min_length=1, max_length=pronounce.MAX_WORD)
    say_as: str = Field(min_length=1, max_length=pronounce.MAX_SAY_AS)

    @model_validator(mode="after")
    def _check(self):
        if msg := pronounce.check_entry(self.word, self.say_as):
            raise ValueError(msg)
        self.word, self.say_as = pronounce.clean_word(self.word), " ".join(self.say_as.split())
        return self


async def _list(db: AsyncSession, user_id: int | None) -> list[Pronunciation]:
    cond = Pronunciation.user_id.is_(None) if user_id is None else Pronunciation.user_id == user_id
    return (await db.execute(select(Pronunciation).where(cond).order_by(Pronunciation.word_key))).scalars().all()


async def _upsert(db: AsyncSession, user_id: int | None, body: EntryIn) -> Pronunciation:
    key = body.word.lower()
    cond = Pronunciation.user_id.is_(None) if user_id is None else Pronunciation.user_id == user_id
    row = (await db.execute(select(Pronunciation).where(cond, Pronunciation.word_key == key))).scalars().first()
    if row is None:
        if user_id is not None:
            n = (await db.execute(select(func.count()).select_from(Pronunciation).where(cond))).scalar_one()
            if n >= pronounce.MAX_PER_USER:
                raise HTTPException(422, f"Your list is full ({pronounce.MAX_PER_USER} words). Remove some first.")
        row = Pronunciation(user_id=user_id, word=body.word, word_key=key, say_as=body.say_as)
        db.add(row)
    else:
        row.word, row.say_as, row.updated_at = body.word, body.say_as, utcnow()
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/pronunciations")
async def list_pronunciations(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    return {"items": [_out(r) for r in await _list(db, p.user.id)],
            "global": [_out(r) for r in await _list(db, None)], "builtin": BUILTIN,
            "can_edit_global": p.user.is_admin and p.via == "session", "max": pronounce.MAX_PER_USER}


@router.post("/pronunciations", dependencies=[Depends(csrf_protect)])
async def save_pronunciation(body: EntryIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    return _out(await _upsert(db, p.user.id, body))


@router.delete("/pronunciations/{entry_id}", dependencies=[Depends(csrf_protect)])
async def delete_pronunciation(entry_id: int, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    row = await db.get(Pronunciation, entry_id)
    if row is None or row.user_id != p.user.id:
        raise HTTPException(404, "Not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


# ── Global list (admins) ──
async def _admin(p: Principal = Depends(current_principal)) -> Principal:
    if not p.user.is_admin or p.via != "session":
        raise HTTPException(404, "Not found")
    return p


@router.post("/admin/pronunciations", dependencies=[Depends(csrf_protect)])
async def save_global(body: EntryIn, p: Principal = Depends(_admin), db: AsyncSession = Depends(get_db)):
    return _out(await _upsert(db, None, body))


@router.delete("/admin/pronunciations/{entry_id}", dependencies=[Depends(csrf_protect)])
async def delete_global(entry_id: int, p: Principal = Depends(_admin), db: AsyncSession = Depends(get_db)):
    row = await db.get(Pronunciation, entry_id)
    if row is None or row.user_id is not None:
        raise HTTPException(404, "Not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


# ── ▶ test ──
class TestIn(BaseModel):
    say_as: str = Field(min_length=1, max_length=pronounce.MAX_SAY_AS)
    voice: str = DEFAULT_VOICE

    @model_validator(mode="after")
    def _check(self):
        if self.voice not in VOICES:
            raise ValueError(f"unknown voice '{self.voice}'")
        if not self.say_as.strip():
            raise ValueError("Type how it should be said")
        return self


@router.post("/pronunciations/test", dependencies=[Depends(csrf_protect)])
async def test_pronunciation(body: TestIn, request: Request, p: Principal = Depends(current_principal)):
    """Short MP3 of `say_as` in the chosen voice. Not saved to History and not counted against the plan."""
    s = get_settings()
    lim = await ratelimit.hit(request.app.state.redis, s.redis_prefix, f"pron-test:user:{p.user.id}", 30, 3600)
    if not lim.allowed:
        raise HTTPException(429, "Too many tests this hour. Try again later.")
    jm = request.app.state.jobs
    if not jm.engine.ready:
        raise HTTPException(503, "TTS engine is still loading, try again in a few seconds")
    v = VOICES[body.voice]
    req = TTSRequest(text=" ".join(body.say_as.split()), engine=v.engine, voice=v.id, lang=v.lang, speed=1.0,
                     format="mp3", loudness_lufs=s.loudness_lufs)
    try:
        job = jm.submit(req, job_id=secrets.token_hex(16), user_id=p.user.id)
    except QueueFull:
        raise HTTPException(429, "The queue is full, please try again in a minute")
    except TooManyPending:
        raise HTTPException(429, "You already have 3 voiceovers waiting. Let one finish first.")
    try:
        await asyncio.wait_for(job.done_event.wait(), TEST_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The queue is busy. Try the test again in a minute.")
    path = jm.audio_path(job.id, "mp3")
    if job.status != "done" or path is None:
        raise HTTPException(422, job.error or "Couldn't make the test audio")
    data = path.read_bytes()
    for ext in ("mp3", "wav", "json"):
        (s.audio_dir / f"{job.id}.{ext}").unlink(missing_ok=True)
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

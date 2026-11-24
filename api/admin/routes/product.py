"""A5: voices & styles (overrides, sample regeneration, studio voices), API keys & usage (all keys, request counts,
rate-limit overrides, top consumers, endpoint error rates, OpenAPI), queue & jobs (live queue, cancel, retry,
failures, throughput, real-time factor, pause / maintenance)."""
import asyncio
import json
import secrets
import shutil
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from db import get_db, utcnow
from models import ApiKey, Generation, RateOverride, StyleSetting, User, VoiceConsent, VoiceSetting
from settings import get_settings
from tts import catalog
from tts.jobs import QueueFull, TooManyPending, TTSRequest
from tts.styles import STYLES
from tts.voices import VOICES

from .. import jobs as bg
from .. import settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
ROOT = bg.ROOT
SAMPLE_TEXT_HI_F = "नमस्ते! मैं आपकी अगली रील के लिए वॉइसओवर तैयार कर सकती हूँ।"
SAMPLE_TEXT_HI_M = "नमस्ते! मैं आपकी अगली रील के लिए वॉइसओवर तैयार कर सकता हूँ।"
SAMPLE_TEXT_EN = "Hi, I'm {name}. I can voice your next reel in seconds."


# ── Voices & styles ──────────────────────────────────────────────────────────
@router.get("/voices")
async def list_voices(request: Request, p: Principal = Depends(require_perm("voices.read")), db: AsyncSession = Depends(get_db)):
    voices = await catalog.builtin_voices(db, p.user, include_disabled=True)
    since = utcnow() - timedelta(days=30)
    usage = dict((await db.execute(select(Generation.voice, func.count()).where(Generation.created_at >= since)
                                   .group_by(Generation.voice))).all())
    for v in voices:
        v["uses_30d"] = usage.get(v["id"], 0)
        v["sample_url"] = f"/samples/{v['id']}.mp3"
    clones = []
    st = await catalog.voice_settings(db)
    for vid, cv in getattr(request.app.state, "clone_voices", {}).items():
        consent = (await db.execute(select(VoiceConsent).where(VoiceConsent.voice_id == vid).order_by(VoiceConsent.id.desc()))).scalars().first()
        d = cv.to_public_dict()
        clones.append(d | catalog.voice_meta(vid, d, st.get(vid), 1000) | {
            "is_public": cv.is_public, "consent": {"status": consent.status, "source_type": consent.source_type,
                                                   "speaker": consent.speaker_name} if consent else None,
            "uses_30d": usage.get(vid, 0)})
    previews = [{"name": n, "url": f"/api/preview/{n}/", "available": (get_settings().data_dir / sub).is_dir()}
                for n, sub in (("voice-lab", "preview/voice-lab"), ("custom-voice", "voices/hi_reel_narrator_m1/lab"))]
    return {"voices": voices, "studio": clones, "styles": await catalog.styles(db, include_disabled=True), "previews": previews,
            "sample_job_running": bg.is_running("voice-sample")}


class VoiceIn(BaseModel):
    enabled: bool = True
    display_name: str = Field("", max_length=40)
    description: str = Field("", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=10)
    sort_order: int = Field(0, ge=0, le=10000)
    is_new: bool = False
    min_plan: str = Field("free", pattern="^(free|starter|creator|pro)$")


@router.put("/voices/{voice_id}")
async def update_voice(voice_id: str, body: VoiceIn, request: Request, p: Principal = Depends(require_perm("voices.write")),
                       db: AsyncSession = Depends(get_db)):
    if voice_id not in VOICES and voice_id not in getattr(request.app.state, "clone_voices", {}):
        raise HTTPException(404, "Unknown voice")
    row = await db.get(VoiceSetting, voice_id)
    before = None
    if row is None:
        row = VoiceSetting(voice_id=voice_id)
        db.add(row)
    else:
        before = {"enabled": row.enabled, "display_name": row.display_name, "description": row.description, "tags": row.tags,
                  "sort_order": row.sort_order, "is_new": row.is_new, "min_plan": row.min_plan}
    row.enabled, row.display_name, row.description = body.enabled, body.display_name.strip(), body.description.strip()
    row.tags = ",".join(t.strip()[:30] for t in body.tags if t.strip())
    row.sort_order, row.is_new, row.min_plan = body.sort_order, body.is_new, body.min_plan
    after = {"enabled": row.enabled, "display_name": row.display_name, "description": row.description, "tags": row.tags,
             "sort_order": row.sort_order, "is_new": row.is_new, "min_plan": row.min_plan}
    audit(db, request, p.user, "voice.update", target_type="voice", target_id=voice_id, label=voice_id, before=before, after=after,
          full=before is None)
    await db.commit()
    catalog.clear_cache()
    return after


class StyleIn(BaseModel):
    enabled: bool = True
    display_name: str = Field("", max_length=40)
    description: str = Field("", max_length=160)
    sort_order: int = Field(0, ge=0, le=10000)


@router.put("/styles/{style_id}")
async def update_style(style_id: str, body: StyleIn, request: Request, p: Principal = Depends(require_perm("voices.write")),
                       db: AsyncSession = Depends(get_db)):
    if style_id not in STYLES:
        raise HTTPException(404, "Unknown style")
    row = await db.get(StyleSetting, style_id) or StyleSetting(style_id=style_id)
    db.add(row)
    row.enabled, row.display_name, row.description, row.sort_order = body.enabled, body.display_name.strip(), body.description.strip(), body.sort_order
    audit(db, request, p.user, "voice.style.update", target_type="style", target_id=style_id, label=style_id, after=body.model_dump(), full=True)
    await db.commit()
    catalog.clear_cache()
    return body.model_dump()


async def _synthesize(request: Request, voice_id: str, text: str) -> bytes:
    jm = request.app.state.jobs
    if not jm.engine.ready:
        raise HTTPException(503, "TTS engine is still loading")
    v = VOICES[voice_id]
    s = get_settings()
    req = TTSRequest(text=text, engine=v.engine, voice=v.id, lang=v.lang, speed=1.0, format="mp3", loudness_lufs=s.loudness_lufs)
    try:
        job = jm.submit(req, job_id=secrets.token_hex(16), user_id=None)
    except (QueueFull, TooManyPending) as e:
        raise HTTPException(429, "The queue is full, try again in a minute") from e
    await asyncio.wait_for(job.done_event.wait(), 120)
    path = jm.audio_path(job.id, "mp3")
    if job.status != "done" or path is None:
        raise HTTPException(422, job.error or "Couldn't make the sample")
    data = path.read_bytes()
    for ext in ("mp3", "wav", "json"):
        (s.audio_dir / f"{job.id}.{ext}").unlink(missing_ok=True)
    return data


@router.post("/voices/{voice_id}/sample")
async def regenerate_sample(voice_id: str, request: Request, p: Principal = Depends(require_perm("voices.write")),
                            db: AsyncSession = Depends(get_db)):
    """Re-make landing/samples/<id>.mp3 with the current engine, publish it to both sites and commit it."""
    if voice_id not in VOICES:
        raise HTTPException(404, "Samples exist for built-in voices only")
    v = VOICES[voice_id]
    name = (await catalog.builtin_voices(db, p.user, include_disabled=True))
    name = next((x["name"] for x in name if x["id"] == voice_id), v.name)
    text = (SAMPLE_TEXT_HI_F if v.gender == "female" else SAMPLE_TEXT_HI_M) if v.lang == "h" else SAMPLE_TEXT_EN.format(name=name)
    data = await _synthesize(request, voice_id, text)
    target = ROOT / "landing" / "samples" / f"{voice_id}.mp3"
    target.write_bytes(data)
    published = []
    for web in ("/www/wwwroot/aiwazz.in/samples", "/www/wwwroot/login.aiwazz.in/samples"):
        if __import__("pathlib").Path(web).is_dir():
            shutil.copyfile(target, f"{web}/{voice_id}.mp3")
            published.append(web)
    audit(db, request, p.user, "voice.sample.regenerate", target_type="voice", target_id=voice_id, label=voice_id,
          after={"bytes": len(data), "published": published}, full=True)
    await db.commit()

    async def commit():
        await bg.run_cmd("git", "add", f"landing/samples/{voice_id}.mp3")
        try:
            await bg.run_cmd("git", "-c", "user.name=AiWazz Admin", "-c", "user.email=admin-panel@aiwazz.in", "commit", "-m",
                             f"Admin: regenerate voice sample {voice_id}\n\nChanged in the admin panel by {p.user.email}.",
                             "--", f"landing/samples/{voice_id}.mp3")
        except RuntimeError as e:
            if "nothing to commit" not in str(e):
                raise
        await bg.run_cmd("git", "push", "-q", "origin", "main", timeout=120)
        return "committed and pushed"
    bg.start(request.app.state.sessionmaker, "voice-sample", commit)
    return {"ok": True, "url": f"/samples/{voice_id}.mp3", "published": len(published)}


class PublishIn(BaseModel):
    public: bool
    reason: str = Field(min_length=3, max_length=255)


@router.post("/voices/{voice_id}/publish")
async def publish_studio_voice(voice_id: str, body: PublishIn, request: Request, p: Principal = Depends(require_perm("voices.write")),
                               _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    """Promote a studio (clone) voice to everyone, or back to owner-only. Owner decision only (CLAUDE.md: not public
    until the owner decides), requires an active consent record; edits data/voices/<id>/voice.json."""
    if p.user.role != "owner":
        raise HTTPException(403, "Only the owner can make a studio voice public")
    cv = getattr(request.app.state, "clone_voices", {}).get(voice_id)
    if cv is None:
        raise HTTPException(404, "Unknown studio voice")
    if body.public:
        ok = await db.scalar(select(VoiceConsent.id).where(VoiceConsent.voice_id == voice_id, VoiceConsent.status == "active").limit(1))
        if not ok:
            raise HTTPException(409, "This voice has no active consent record (manage.py add-voice-consent)")
    path = get_settings().data_dir / "voices" / voice_id / "voice.json"
    data = json.loads(path.read_text())
    before = data.get("is_public", False)
    data["is_public"] = body.public
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    from tts.clone_voices import load_clone_voices
    request.app.state.clone_voices = load_clone_voices(get_settings().data_dir / "voices")
    audit(db, request, p.user, "voice.studio.publish" if body.public else "voice.studio.unpublish", target_type="voice",
          target_id=voice_id, label=cv.name, before={"is_public": before}, after={"is_public": body.public}, reason=body.reason)
    await db.commit()
    return {"ok": True, "is_public": body.public}


# ── API & usage ──────────────────────────────────────────────────────────────
async def _key_counts(request: Request, hours: int, days: int) -> tuple[dict[int, int], dict[int, int]]:
    redis, pfx, now = request.app.state.redis, get_settings().redis_prefix, utcnow()
    h24: dict[int, int] = {}
    for i in range(hours):
        for k, v in (await redis.hgetall(f"{pfx}apikey:h:{now - timedelta(hours=i):%Y%m%d%H}")).items():
            h24[int(k)] = h24.get(int(k), 0) + int(v)
    d30: dict[int, int] = {}
    for i in range(days):
        for k, v in (await redis.hgetall(f"{pfx}apikey:d:{now - timedelta(days=i):%Y%m%d}")).items():
            d30[int(k)] = d30.get(int(k), 0) + int(v)
    return h24, d30


@router.get("/api-keys")
async def all_keys(request: Request, lp: ListParams = Depends(), status: str = Query("active", pattern="^(|active|revoked)$"),
                   p: Principal = Depends(require_perm("api.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(ApiKey, User.email).join(User, User.id == ApiKey.user_id)
    if status == "active":
        stmt = stmt.where(ApiKey.revoked_at.is_(None))
    elif status == "revoked":
        stmt = stmt.where(ApiKey.revoked_at.is_not(None))
    if lp.q:
        stmt = stmt.where(or_(User.email.contains(lp.q.lower()), ApiKey.prefix.contains(lp.q), ApiKey.name.contains(lp.q)))
    h24, d30 = await _key_counts(request, 24, 30)
    overrides = {(o.scope, o.target_id): o.rpm for o in (await db.execute(select(RateOverride))).scalars()}
    return await respond(db, request, p, stmt, lp, scalars=False, name="api-keys",
                         sorts={"created_at": ApiKey.created_at, "last_used": ApiKey.last_used_at}, default_sort=ApiKey.id.desc(),
                         row=lambda r: {"id": r[0].id, "name": r[0].name, "prefix": r[0].prefix, "user_id": r[0].user_id, "email": r[1],
                                        "created_at": iso(r[0].created_at), "last_used_at": iso(r[0].last_used_at),
                                        "revoked_at": iso(r[0].revoked_at), "requests_24h": h24.get(r[0].id, 0),
                                        "requests_30d": d30.get(r[0].id, 0),
                                        "rpm_override": overrides.get(("key", r[0].id)) or overrides.get(("user", r[0].user_id))})


@router.post("/api-keys/{kid}/revoke")
async def revoke_any_key(kid: int, request: Request, p: Principal = Depends(require_perm("api.write")), db: AsyncSession = Depends(get_db)):
    k = await db.get(ApiKey, kid)
    if k is None or k.revoked_at:
        raise HTTPException(404, "API key not found")
    k.revoked_at = utcnow()
    audit(db, request, p.user, "api.key.revoke", target_type="api_key", target_id=k.id, label=f"{k.prefix}… ({k.user.email})")
    await db.commit()
    return {"ok": True}


@router.get("/api/usage")
async def api_usage(request: Request, p: Principal = Depends(require_perm("api.read")), db: AsyncSession = Depends(get_db)):
    """Top consumers (characters, 30 days, web vs API), endpoint error rates (7 days) and the default rate limit."""
    since = utcnow() - timedelta(days=30)
    top = (await db.execute(select(User.id, User.email, func.sum(Generation.text_chars), func.count(),
                                   func.sum(case((Generation.api_key_id.is_not(None), 1), else_=0)))
                            .join(Generation, Generation.user_id == User.id)
                            .where(Generation.created_at >= since, Generation.status == "done")
                            .group_by(User.id, User.email).order_by(func.sum(Generation.text_chars).desc()).limit(15))).all()
    redis, pfx, now = request.app.state.redis, get_settings().redis_prefix, utcnow()
    eps: dict[str, dict[str, int]] = {}
    for i in range(7):
        for field, v in (await redis.hgetall(f"{pfx}reqstats:{now - timedelta(days=i):%Y%m%d}")).items():
            ep, cls = field.rsplit("|", 1)
            e = eps.setdefault(ep, {"total": 0, "4xx": 0, "5xx": 0})
            e["total"] += int(v)
            if cls in ("4xx", "5xx"):
                e[cls] += int(v)
    endpoints = sorted(({"endpoint": k, **v, "error_rate": round((v["4xx"] + v["5xx"]) / v["total"] * 100, 1) if v["total"] else 0}
                        for k, v in eps.items()), key=lambda x: -x["total"])
    overrides = (await db.execute(select(RateOverride).order_by(RateOverride.id.desc()))).scalars().all()
    return {
        "top": [{"user_id": uid, "email": email, "chars": int(chars or 0), "generations": n, "api_generations": int(api or 0)}
                for uid, email, chars, n, api in top],
        "endpoints": endpoints[:40], "default_rpm": (await settings_store.get(db, "limits"))["api_rpm"],
        "overrides": [{"id": o.id, "scope": o.scope, "target_id": o.target_id, "rpm": o.rpm, "note": o.note, "created_at": iso(o.created_at)}
                      for o in overrides],
    }


class OverrideIn(BaseModel):
    scope: str = Field(pattern="^(key|user)$")
    target_id: int = Field(ge=1)
    rpm: int = Field(ge=1, le=10000)
    note: str = Field("", max_length=255)


@router.post("/api/rate-overrides")
async def set_override(body: OverrideIn, request: Request, p: Principal = Depends(require_perm("api.write")), db: AsyncSession = Depends(get_db)):
    target = await db.get(ApiKey if body.scope == "key" else User, body.target_id)
    if target is None:
        raise HTTPException(404, f"No such {body.scope}")
    row = (await db.execute(select(RateOverride).where(RateOverride.scope == body.scope, RateOverride.target_id == body.target_id))).scalar_one_or_none()
    if row is None:
        row = RateOverride(scope=body.scope, target_id=body.target_id, rpm=body.rpm)
        db.add(row)
    row.rpm, row.note = body.rpm, body.note
    audit(db, request, p.user, "api.rate_override.set", target_type=body.scope, target_id=body.target_id, after=body.model_dump(), full=True)
    await db.commit()
    return {"ok": True}


@router.delete("/api/rate-overrides/{oid}")
async def delete_override(oid: int, request: Request, p: Principal = Depends(require_perm("api.write")), db: AsyncSession = Depends(get_db)):
    row = await db.get(RateOverride, oid)
    if row is None:
        raise HTTPException(404, "Not found")
    audit(db, request, p.user, "api.rate_override.delete", target_type=row.scope, target_id=row.target_id, before={"rpm": row.rpm}, full=True)
    await db.delete(row)
    await db.commit()
    return {"ok": True}


class LimitsIn(BaseModel):
    api_rpm: int = Field(ge=1, le=10000)


@router.put("/settings/limits/api")
async def set_default_rpm(body: LimitsIn, request: Request, p: Principal = Depends(require_perm("api.write")), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "limits")
    after = {**before, "api_rpm": body.api_rpm}
    await settings_store.put(db, "limits", after, p.user.id)
    audit(db, request, p.user, "settings.limits.api_rpm", target_type="setting", target_id="limits", before=before, after=after)
    await db.commit()
    return after


@router.get("/api/openapi")
async def admin_openapi(request: Request, p: Principal = Depends(require_perm("api.read"))):
    """The public API description (docs are off in production; staff can read them here)."""
    spec = request.app.openapi()
    paths = {k: v for k, v in spec.get("paths", {}).items() if not k.startswith("/api/admin")}
    return spec | {"paths": paths}


# ── Queue & jobs ─────────────────────────────────────────────────────────────
@router.get("/queue")
async def queue_state(request: Request, p: Principal = Depends(require_perm("queue.read")), db: AsyncSession = Depends(get_db)):
    jm = request.app.state.jobs
    now_ts = __import__("time").time()
    ids = [j for j in ([jm.running] if jm.running else []) + list(jm.pending) + ([jm.clone_running] if jm.clone_running else []) + list(jm.clone_pending) if j]
    users = dict((await db.execute(select(User.id, User.email).where(User.id.in_(
        [jm.jobs[i].user_id for i in ids if i in jm.jobs and jm.jobs[i].user_id])))).all()) if ids else {}

    def jrow(jid, where):
        j = jm.jobs.get(jid)
        if j is None:
            return None
        return {"id": j.id, "where": where, "status": j.status, "stage": j.stage, "progress": round(j.progress, 3),
                "user_id": j.user_id, "email": users.get(j.user_id, "system"), "chars": len(j.req.text), "voice": j.req.voice,
                "waiting_sec": int(now_ts - j.created_at), "position": jm.position(j) if where == "queue" else None}
    running = [r for r in [jrow(jm.running, "running") if jm.running else None, jrow(jm.clone_running, "studio") if jm.clone_running else None] if r]
    waiting = [r for r in [jrow(j, "queue") for j in jm.pending] + [jrow(j, "studio-queue") for j in jm.clone_pending] if r]
    since = utcnow() - timedelta(hours=24)
    hours = (await db.execute(select(Generation.created_at, Generation.status, Generation.duration_sec, Generation.compute_sec)
                              .where(Generation.created_at >= since))).all()
    buckets: dict[str, dict] = {}
    for created, status, dur, comp in hours:
        k = f"{created + timedelta(hours=5, minutes=30):%Y-%m-%d %H}:00"
        b = buckets.setdefault(k, {"hour": k, "done": 0, "error": 0})
        if status in ("done", "error"):
            b[status] += 1
    rtf = (await db.execute(select(func.sum(Generation.compute_sec), func.sum(Generation.duration_sec)).where(
        Generation.created_at >= utcnow() - timedelta(days=7), Generation.status == "done", Generation.compute_sec.is_not(None)))).one()
    ops = await settings_store.get(db, "ops")
    return {"running": running, "waiting": waiting, "paused": jm.paused, "maintenance": jm.maintenance, "message": ops.get("message", ""),
            "engine_ready": jm.engine.ready, "max_queue": jm.s.max_queue,
            "throughput": sorted(buckets.values(), key=lambda b: b["hour"]),
            "rtf_7d": round(rtf[0] / rtf[1], 2) if rtf[0] and rtf[1] else None}


@router.post("/queue/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request, p: Principal = Depends(require_perm("queue.write")), db: AsyncSession = Depends(get_db)):
    jm = request.app.state.jobs
    job = jm.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if not await jm.cancel(job_id):
        raise HTTPException(409, "Only waiting jobs can be cancelled (a running job finishes in a few seconds)")
    audit(db, request, p.user, "queue.job.cancel", target_type="generation", target_id=job_id, label=f"user #{job.user_id}")
    await db.commit()
    return {"ok": True}


@router.post("/queue/{job_id}/retry")
async def retry_job(job_id: str, request: Request, p: Principal = Depends(require_perm("queue.write")), db: AsyncSession = Depends(get_db)):
    """Run a failed job again for its owner (new history entry). Only while the script is still in memory: scripts
    are never stored, so after a restart a failed job can't be retried here (the user just generates again)."""
    jm = request.app.state.jobs
    old = jm.jobs.get(job_id)
    gen = await db.get(Generation, job_id)
    if gen is None:
        raise HTTPException(404, "Job not found")
    if gen.status != "error":
        raise HTTPException(409, "Only failed jobs can be retried")
    if old is None:
        raise HTTPException(410, "The script isn't kept after a restart, so this job can't be retried. The user can generate it again.")
    new_id = secrets.token_hex(16)
    db.add(Generation(id=new_id, user_id=gen.user_id, api_key_id=gen.api_key_id, engine=gen.engine, voice=gen.voice, lang=gen.lang,
                      speed=gen.speed, format=gen.format, loudness_target=gen.loudness_target, style=gen.style,
                      text_chars=gen.text_chars, text_excerpt=gen.text_excerpt))
    await db.commit()
    try:
        jm.submit(old.req, job_id=new_id, user_id=old.user_id)
    except (QueueFull, TooManyPending) as e:
        await db.delete(await db.get(Generation, new_id))
        await db.commit()
        raise HTTPException(429, "The queue is full right now") from e
    audit(db, request, p.user, "queue.job.retry", target_type="generation", target_id=job_id, after={"new_id": new_id}, full=True)
    await db.commit()
    return {"ok": True, "id": new_id}


@router.get("/queue/failures")
async def failures(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("queue.read")),
                   db: AsyncSession = Depends(get_db)):
    jm = request.app.state.jobs
    stmt = select(Generation, User.email).join(User, User.id == Generation.user_id).where(Generation.status == "error")
    return await respond(db, request, p, stmt, lp, scalars=False, name="failed-jobs", sorts={"created_at": Generation.created_at},
                         default_sort=Generation.created_at.desc(),
                         row=lambda r: {"id": r[0].id, "user_id": r[0].user_id, "email": r[1], "voice": r[0].voice, "chars": r[0].text_chars,
                                        "error": r[0].error, "created_at": iso(r[0].created_at), "retryable": r[0].id in jm.jobs})


class OpsIn(BaseModel):
    queue_paused: bool
    maintenance: bool
    message: str = Field("", max_length=300)


@router.put("/queue/ops")
async def set_ops(body: OpsIn, request: Request, p: Principal = Depends(require_perm("maintenance.write")),
                  _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "ops")
    after = body.model_dump()
    await settings_store.put(db, "ops", after, p.user.id)
    jm = request.app.state.jobs
    jm.set_paused(body.queue_paused)
    jm.maintenance, jm.maintenance_message = body.maintenance, body.message
    audit(db, request, p.user, "queue.ops", target_type="setting", target_id="ops", before=before, after=after)
    await db.commit()
    return after

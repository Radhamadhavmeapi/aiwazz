"""A8: Analytics from metrics_daily (+ live today): range + compare, funnel (visitors → signups → first
generation → paid), weekly cohort retention, voice/style/language popularity, Hinglish usage, script length,
API vs web, top users, revenue by plan and by state."""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from billing.gst import STATES
from db import get_db
from models import Generation, MetricDaily, User
from tts.styles import STYLES
from tts.voices import VOICES

from .. import metrics
from ..audit import audit
from ..deps import require_perm, staff_principal

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)


async def _range(db: AsyncSession, start: date, end: date) -> dict[str, dict[str, float]]:
    """{day: {key: value}} for [start, end] inclusive; today (IST) live."""
    rows = (await db.execute(select(MetricDaily).where(MetricDaily.day >= start.isoformat(), MetricDaily.day <= end.isoformat()))).scalars()
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        out[r.day][r.key] = r.value
    today = metrics.today_ist()
    if start <= today <= end:
        v = metrics.visits_for({today}) if metrics.log_covers(today) else {}
        out[today.isoformat()] = await metrics.compute_day(db, today, v.get(today))
    return out


def _sum(days: dict[str, dict[str, float]]) -> dict[str, float]:
    t: dict[str, float] = defaultdict(float)
    for vals in days.values():
        for k, v in vals.items():
            t[k] += v
    return t


def _series(days: dict, start: date, end: date, key: str) -> list[dict]:
    n = (end - start).days + 1
    return [{"date": (start + timedelta(days=i)).isoformat(), "value": days.get((start + timedelta(days=i)).isoformat(), {}).get(key, 0)}
            for i in range(n)]


def _top(totals: dict[str, float], prefix: str, names: dict[str, str] | None = None, limit: int = 12) -> list[dict]:
    items = [(k[len(prefix):], v) for k, v in totals.items() if k.startswith(prefix)]
    items.sort(key=lambda x: -x[1])
    return [{"id": i, "name": (names or {}).get(i, i), "value": v} for i, v in items[:limit]]


async def _cohorts(db: AsyncSession, weeks: int = 8) -> list[dict]:
    """Weekly signup cohorts (IST weeks starting Monday): % of the cohort that made a voiceover in week 0, 1, 2…"""
    today = metrics.today_ist()
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=weeks - 1)
    a, _ = metrics.ist_day_bounds(first)
    users = (await db.execute(select(User.id, User.created_at).where(User.created_at >= a, User.role == "user"))).all()
    gens = (await db.execute(select(Generation.user_id, Generation.created_at).where(Generation.created_at >= a, Generation.status == "done"))).all()
    active: dict[int, set[int]] = defaultdict(set)
    cohort_of: dict[int, date] = {}
    for uid, created in users:
        d = (created + metrics.IST).date()
        cohort_of[uid] = d - timedelta(days=d.weekday())
    for uid, created in gens:
        if uid in cohort_of:
            wk = ((created + metrics.IST).date() - cohort_of[uid]).days // 7
            if wk >= 0:
                active[uid].add(wk)
    out = []
    for i in range(weeks):
        start = first + timedelta(weeks=i)
        members = [u for u, c in cohort_of.items() if c == start]
        max_w = (monday - start).days // 7
        cells = [round(sum(1 for u in members if w in active[u]) / len(members) * 100) if members else None for w in range(max_w + 1)]
        out.append({"week": start.isoformat(), "size": len(members), "retention": cells})
    return out


@router.get("/analytics")
async def analytics(request: Request, start: date = Query(...), end: date = Query(...), compare: bool = True,
                    p: Principal = Depends(require_perm("analytics.read")), db: AsyncSession = Depends(get_db)):
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Pick a range of up to one year")
    days = await _range(db, start, end)
    t = _sum(days)
    prev = None
    if compare:
        n = (end - start).days + 1
        prev = _sum(await _range(db, start - timedelta(days=n), start - timedelta(days=1)))
    done = t.get("generations_done", 0)
    a, b = metrics.ist_day_bounds(start)[0], metrics.ist_day_bounds(end)[1]
    top_users = (await db.execute(select(User.id, User.email, func.sum(Generation.text_chars), func.count())
                                  .join(Generation, Generation.user_id == User.id)
                                  .where(Generation.created_at >= a, Generation.created_at < b, Generation.status == "done")
                                  .group_by(User.id, User.email).order_by(func.sum(Generation.text_chars).desc()).limit(10))).all()
    can_users = "users.read" in __import__("admin.rbac", fromlist=["perms_for"]).perms_for(p.user.role)
    keys = ("visitors", "page_views", "signups", "first_generation", "paid_new", "generations", "generations_done", "chars",
            "revenue_paise", "refunds_paise", "active_users", "hinglish", "api_generations", "web_generations")
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": {k: t.get(k, 0) for k in keys}, "previous": {k: prev.get(k, 0) for k in keys} if prev is not None else None,
        "series": {k: _series(days, start, end, k) for k in ("visitors", "signups", "generations_done", "revenue_paise", "chars")},
        "funnel": [{"step": "Visitors (aiwazz.in)", "value": t.get("visitors", 0)}, {"step": "Signups", "value": t.get("signups", 0)},
                   {"step": "First voiceover", "value": t.get("first_generation", 0)}, {"step": "First payment", "value": t.get("paid_new", 0)}],
        "popularity": {"voices": _top(t, "voice:", {k: f"{v.name} ({k})" for k, v in VOICES.items()}),
                       "styles": _top(t, "style:", {k: s.name for k, s in STYLES.items()}),
                       "languages": _top(t, "lang:", {"h": "Hindi", "a": "English (US)", "b": "English (UK)"})},
        "hinglish_pct": round(t.get("hinglish", 0) / done * 100, 1) if done else None,
        "avg_script_chars": round(t.get("script_chars", 0) / t.get("generations", 1)) if t.get("generations") else None,
        "api_vs_web": {"api": t.get("api_generations", 0), "web": t.get("web_generations", 0)},
        "rtf": round(t["compute_sec"] / t["audio_sec"], 2) if t.get("audio_sec") else None,
        "chars_by_plan": _top(t, "chars_plan:", {"free": "Free", "starter": "Starter", "creator": "Creator", "pro": "Pro"}),
        "revenue_by_plan": _top(t, "revenue_plan:", {"starter": "Starter", "creator": "Creator", "pro": "Pro"}),
        "revenue_by_state": _top(t, "revenue_state:", STATES, limit=40),
        "top_users": [{"user_id": u, "email": e if can_users else f"user #{u}", "chars": int(c or 0), "generations": n} for u, e, c, n in top_users],
        "cohorts": await _cohorts(db),
        "visits_note": "Counted from the aiwazz.in nginx access log (human page views, bots and assets excluded); days before the "
                       "current log file was rotated show 0.",
    }


@router.post("/analytics/rebuild")
async def rebuild(request: Request, p: Principal = Depends(require_perm("system.write")), db: AsyncSession = Depends(get_db)):
    """Recompute the last 60 days of metrics_daily (e.g. after a correction)."""
    from models import MetricDaily
    from sqlalchemy import delete
    await db.execute(delete(MetricDaily))
    await db.commit()
    note = await metrics.nightly(db)
    audit(db, request, p.user, "system.metrics.rebuild", target_type="metrics", after={"note": note}, full=True)
    await db.commit()
    return {"note": note}

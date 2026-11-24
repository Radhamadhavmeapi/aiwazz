"""Analytics aggregation (A8). compute_day() builds every metric for one IST day from the database and the landing
page's nginx access log (no third-party trackers; IPs are only used in memory to count unique visitors and are never
stored). store_day() writes them to metrics_daily; the nightly task fills yesterday and back-fills missing days."""
import hashlib
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import Generation, Invoice, MetricDaily, Payment, Subscription, User

IST = timedelta(hours=5, minutes=30)
ACCESS_LOG = Path("/www/wwwlogs/aiwazz.in.log")
SERVER_IPS = {"104.237.6.214", "127.0.0.1"}
_LOG = re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" (?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"')
_ASSET = re.compile(r"\.(css|js|mjs|png|jpe?g|webp|avif|gif|svg|ico|xml|txt|mp3|wav|json|woff2?|map|webmanifest)$|^/(_astro|fonts|samples|media|api)/", re.I)
_BOT = re.compile(r"bot|crawl|spider|slurp|curl|wget|python|httpx|go-http|java|lighthouse|headless|monitor|uptime|preview|facebookexternalhit|scan", re.I)


def ist_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day) - IST
    return start, start + timedelta(days=1)


def today_ist() -> date:
    return (utcnow() + IST).date()


def visits_for(days: set[date], path: Path = ACCESS_LOG) -> dict[date, tuple[int, int]]:
    """{day: (page views, unique visitors)} for human page views on aiwazz.in (GET, 200, not assets, not bots)."""
    out: dict[date, list] = {d: [0, set()] for d in days}
    if not path.is_file() or not days:
        return {d: (0, 0) for d in days}
    with path.open("r", errors="replace") as f:
        for line in f:
            m = _LOG.match(line)
            if not m or m["method"] != "GET" or m["status"] != "200" or m["ip"] in SERVER_IPS:
                continue
            p = m["path"].split("?")[0]
            if _ASSET.search(p) or _BOT.search(m["ua"]):
                continue
            try:
                ts = datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z")
            except ValueError:
                continue
            d = ((ts - ts.utcoffset()).replace(tzinfo=None) + IST).date()
            if d in out:
                out[d][0] += 1
                out[d][1].add(hashlib.sha256(f"{m['ip']}|{m['ua']}|{d}".encode()).hexdigest()[:16])
    return {d: (v[0], len(v[1])) for d, v in out.items()}


def log_covers(d: date, path: Path = ACCESS_LOG) -> bool:
    """True if the current access log reaches back to day d (older days were rotated away)."""
    if not path.is_file():
        return False
    with path.open("r", errors="replace") as f:
        first = f.readline()
    m = _LOG.match(first)
    if not m:
        return False
    ts = datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z")
    return ((ts - ts.utcoffset()).replace(tzinfo=None) + IST).date() <= d


async def compute_day(db: AsyncSession, d: date, visits: tuple[int, int] | None = None) -> dict[str, float]:
    a, b = ist_day_bounds(d)
    m: Counter = Counter()
    m["signups"] = (await db.execute(select(func.count()).select_from(User).where(User.created_at >= a, User.created_at < b))).scalar_one()
    gens = (await db.execute(select(Generation.status, Generation.voice, Generation.style, Generation.lang, Generation.text_chars,
                                    Generation.api_key_id, Generation.transliterate, Generation.user_id, Generation.compute_sec,
                                    Generation.duration_sec).where(Generation.created_at >= a, Generation.created_at < b))).all()
    plans = dict((await db.execute(select(User.id, User.plan))).all())
    active = set()
    for st, voice, style, lang, chars, key, translit, uid, comp, dur in gens:
        m["generations"] += 1
        m["script_chars"] += chars or 0
        if st == "error":
            m["generations_failed"] += 1
            continue
        if st != "done":
            continue
        active.add(uid)
        m["generations_done"] += 1
        m["chars"] += chars or 0
        m[f"voice:{voice}"] += 1
        m[f"lang:{lang}"] += 1
        if style:
            m[f"style:{style}"] += 1
        m["api_generations" if key else "web_generations"] += 1
        if translit:
            m["hinglish"] += 1
        m[f"chars_plan:{plans.get(uid, 'free')}"] += chars or 0
        if comp and dur:
            m["compute_sec"] += comp
            m["audio_sec"] += dur
    m["active_users"] = len(active)
    first = select(Generation.user_id, func.min(Generation.created_at).label("f")).group_by(Generation.user_id).subquery()
    m["first_generation"] = (await db.execute(select(func.count()).select_from(first).where(first.c.f >= a, first.c.f < b))).scalar_one()
    firstpay = select(Payment.user_id, func.min(Payment.created_at).label("f")).where(Payment.status.in_(("captured", "refunded"))) \
        .group_by(Payment.user_id).subquery()
    m["paid_new"] = (await db.execute(select(func.count()).select_from(firstpay).where(firstpay.c.f >= a, firstpay.c.f < b))).scalar_one()
    pays = (await db.execute(select(Payment.amount_paise, Subscription.plan, Invoice.buyer_state, Invoice.taxable_paise)
                             .outerjoin(Subscription, Subscription.id == Payment.subscription_id)
                             .outerjoin(Invoice, Invoice.payment_id == Payment.id)
                             .where(Payment.status.in_(("captured", "refunded")), Payment.created_at >= a, Payment.created_at < b))).all()
    for amount, plan, state, taxable in pays:
        m["revenue_paise"] += amount
        m["payments"] += 1
        m[f"revenue_plan:{plan or 'other'}"] += amount
        if state:
            m[f"revenue_state:{state}"] += taxable or 0
    try:
        from models import Refund
        m["refunds_paise"] = (await db.execute(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
            Refund.status == "processed", Refund.processed_at >= a, Refund.processed_at < b))).scalar_one()
    except ImportError:
        pass
    if visits is not None:
        m["page_views"], m["visitors"] = visits
    return {k: float(v) for k, v in m.items() if v}


async def store_day(db: AsyncSession, d: date, values: dict[str, float]) -> None:
    await db.execute(delete(MetricDaily).where(MetricDaily.day == d.isoformat()))
    db.add(MetricDaily(day=d.isoformat(), key="_computed", value=1))     # marks quiet days as done too
    for k, v in values.items():
        db.add(MetricDaily(day=d.isoformat(), key=k[:64], value=v))
    await db.commit()


async def nightly(db: AsyncSession, backfill_days: int = 60) -> str:
    """Compute yesterday (always) and any missing day in the last `backfill_days`. Idempotent."""
    today = today_ist()
    have = set((await db.execute(select(MetricDaily.day).distinct())).scalars())
    first_user = (await db.execute(select(func.min(User.created_at)))).scalar()
    oldest = max(today - timedelta(days=backfill_days), ((first_user + IST).date() if first_user else today))
    todo = [d for d in (today - timedelta(days=i) for i in range(1, backfill_days + 1))
            if d >= oldest and (d.isoformat() not in have or d == today - timedelta(days=1))]
    visits = visits_for({d for d in todo if log_covers(d)})
    for d in todo:
        await store_day(db, d, await compute_day(db, d, visits.get(d)))
    return f"{len(todo)} day(s) computed"

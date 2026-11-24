"""A2: Overview (KPIs with trend vs previous period, charts, latest lists), global search, notifications bell."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from billing.gst import plan_prices
from db import get_db, utcnow
from models import ContactMessage, Generation, Invoice, InviteRequest, Payment, Subscription, User
from usage import PLANS, period_bounds

from .. import rbac
from ..deps import require_perm, require_unlocked, staff_principal
from ..listing import iso

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
IST = timedelta(hours=5, minutes=30)
PAID_ACTIVE = ("active", "authenticated", "pending")


def ist_midnight(now: datetime | None = None) -> datetime:
    """Start of today in India, as naive UTC."""
    n = (now or utcnow()) + IST
    return n.replace(hour=0, minute=0, second=0, microsecond=0) - IST


def monthly_paise(plan: str, period: str) -> int:
    """Monthly recurring revenue of one subscription, excl. GST (yearly / 12)."""
    p = plan_prices().get(plan)
    if not p:
        return 0
    return round(p["yearly"] * 100 / 12) if period == "yearly" else p["monthly"] * 100


def pct(cur: float, prev: float) -> float | None:
    if not prev:
        return None if not cur else 100.0
    return (cur - prev) / prev * 100


async def _count(db, model, *conds) -> int:
    return int((await db.execute(select(func.count()).select_from(model).where(*conds))).scalar_one())


async def _sum(db, col, *conds) -> int:
    return int((await db.execute(select(func.coalesce(func.sum(col), 0)).where(*conds))).scalar_one())


async def refunds_between(db, start, end) -> int:
    try:
        from models import Refund
    except ImportError:
        return 0
    return await _sum(db, Refund.amount_paise, Refund.status == "processed", Refund.created_at >= start, Refund.created_at < end)


async def mrr_at(db: AsyncSession, at: datetime) -> tuple[int, int]:
    """(MRR paise, paying subscriptions) for subscriptions that were active at `at` (by their period dates)."""
    rows = (await db.execute(select(Subscription.plan, Subscription.period).where(
        Subscription.status.in_(PAID_ACTIVE + ("cancelled", "halted", "completed")),
        Subscription.current_start.is_not(None), Subscription.current_start <= at,
        or_(Subscription.current_end.is_(None), Subscription.current_end > at)))).all()
    return sum(monthly_paise(p, per) for p, per in rows), len(rows)


async def daily_series(db: AsyncSession, col_date, value, *conds, days: int = 30) -> list[dict]:
    """[{date, value}] for the last `days` IST days (missing days = 0). col_date: a UTC DateTime column."""
    start = ist_midnight() - timedelta(days=days - 1)
    from sqlalchemy import literal
    rows = (await db.execute(select(col_date, literal(value) if isinstance(value, int) else value)
                             .where(col_date >= start, *conds))).all()
    buckets: dict[str, float] = {}
    for ts, v in rows:
        d = (ts + IST).date().isoformat()
        buckets[d] = buckets.get(d, 0) + (v or 0)
    out = []
    for i in range(days):
        d = (start + IST + timedelta(days=i)).date().isoformat()
        out.append({"date": d, "value": buckets.get(d, 0)})
    return out


@router.get("/overview")
async def overview(p: Principal = Depends(require_perm("overview.read")), db: AsyncSession = Depends(get_db)):
    now = utcnow()
    today = ist_midnight(now)
    m_start, m_end = period_bounds(now)
    prev_m_start, _ = period_bounds(m_start - timedelta(days=1))
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)

    mrr, paying = await mrr_at(db, now)
    mrr_prev, paying_prev = await mrr_at(db, d30)
    signups = {k: await _count(db, User, User.created_at >= since) for k, since in
               (("today", today), ("d7", now - timedelta(days=7)), ("d30", d30))}
    signups_prev30 = await _count(db, User, User.created_at >= d60, User.created_at < d30)
    total_users = await _count(db, User)
    ever_paid = int((await db.execute(select(func.count(func.distinct(Payment.user_id))).where(Payment.status == "captured"))).scalar_one())
    # Churn (30 days): subscriptions that ended (cancelled/halted/completed with period end in the window) vs paying 30 days ago
    churned = (await db.execute(select(Subscription.plan, Subscription.period).where(
        Subscription.status.in_(("cancelled", "halted", "completed")), Subscription.current_end >= d30,
        Subscription.current_end < now))).all()
    churn_logo = len(churned) / paying_prev * 100 if paying_prev else 0.0
    churn_rev = sum(monthly_paise(a, b) for a, b in churned) / mrr_prev * 100 if mrr_prev else 0.0
    paid_month = await _sum(db, Payment.amount_paise, Payment.status == "captured", Payment.created_at >= m_start)
    paid_prev = await _sum(db, Payment.amount_paise, Payment.status == "captured", Payment.created_at >= prev_m_start,
                           Payment.created_at < m_start)
    net_month = paid_month - await refunds_between(db, m_start, m_end)
    net_prev = paid_prev - await refunds_between(db, prev_m_start, m_start)
    chars_today = await _sum(db, Generation.text_chars, Generation.status == "done", Generation.created_at >= today)
    chars_yday = await _sum(db, Generation.text_chars, Generation.status == "done", Generation.created_at >= today - timedelta(days=1),
                            Generation.created_at < today)
    chars_month = await _sum(db, Generation.text_chars, Generation.status == "done", Generation.created_at >= m_start)
    gens_today = await _count(db, Generation, Generation.created_at >= today)
    gens_yday = await _count(db, Generation, Generation.created_at >= today - timedelta(days=1), Generation.created_at < today)
    failed_24 = await _count(db, Generation, Generation.status == "error", Generation.created_at >= now - timedelta(hours=24))
    failed_pay_7 = await _count(db, Payment, Payment.status == "failed", Payment.created_at >= now - timedelta(days=7))
    # Average queue wait (last 24 h): total time minus compute time
    waits = (await db.execute(select(Generation.created_at, Generation.finished_at, Generation.compute_sec).where(
        Generation.status == "done", Generation.finished_at.is_not(None), Generation.created_at >= now - timedelta(hours=24)))).all()
    wait_vals = [max(0.0, (f - c).total_seconds() - (cs or 0)) for c, f, cs in waits]
    avg_wait = sum(wait_vals) / len(wait_vals) if wait_vals else None

    kpis = {
        "mrr_paise": mrr, "mrr_trend": pct(mrr, mrr_prev), "arr_paise": mrr * 12,
        "paying": paying, "paying_trend": pct(paying, paying_prev),
        "signups": signups, "signups_trend": pct(signups["d30"], signups_prev30), "total_users": total_users,
        "free_to_paid_pct": ever_paid / total_users * 100 if total_users else 0.0,
        "trial_to_paid_pct": None,   # no free trials exist (early access = time-limited plan); shown as n/a
        "churn_logo_pct": churn_logo, "churn_revenue_pct": churn_rev,
        "arpu_paise": round(mrr / paying) if paying else 0,
        "net_revenue_month_paise": net_month, "net_revenue_trend": pct(net_month, net_prev),
        "chars_today": chars_today, "chars_today_trend": pct(chars_today, chars_yday), "chars_month": chars_month,
        "generations_today": gens_today, "generations_trend": pct(gens_today, gens_yday),
        "avg_queue_wait_sec": avg_wait, "failed_jobs_24h": failed_24, "failed_payments_7d": failed_pay_7,
    }

    # Charts (30 days, IST days)
    revenue = await daily_series(db, Payment.created_at, Payment.amount_paise, Payment.status == "captured")
    signups_s = await daily_series(db, User.created_at, 1)
    gens_s = await daily_series(db, Generation.created_at, 1)
    # Characters this month by the user's current plan; plan mix = users by effective plan
    rows = (await db.execute(select(User.plan, User.plan_until, func.coalesce(func.sum(Generation.text_chars), 0))
                             .join(Generation, Generation.user_id == User.id)
                             .where(Generation.status == "done", Generation.created_at >= m_start)
                             .group_by(User.id, User.plan, User.plan_until))).all()
    by_plan: dict[str, int] = {}
    for plan, until, n in rows:
        eff = "free" if until is not None and until <= now else plan
        by_plan[eff] = by_plan.get(eff, 0) + int(n)
    mix: dict[str, int] = {}
    for plan, until in (await db.execute(select(User.plan, User.plan_until).where(User.role == "user"))).all():
        eff = "free" if until is not None and until <= now else plan
        mix[eff] = mix.get(eff, 0) + 1
    names = {k: v["name"] for k, v in PLANS.items()}

    can = lambda perm: rbac.has(p.user.role, perm)  # noqa: E731
    latest_signups = [{"id": u.id, "email": u.email, "plan": u.effective_plan, "created_at": iso(u.created_at)} for u in
                      (await db.execute(select(User).order_by(User.id.desc()).limit(6))).scalars()] if can("users.read") else []
    latest_payments = [{"id": x.id, "rzp_payment_id": x.rzp_payment_id, "amount_paise": x.amount_paise, "status": x.status,
                        "user_id": x.user_id, "created_at": iso(x.created_at)} for x in
                       (await db.execute(select(Payment).order_by(Payment.id.desc()).limit(6))).scalars()] if can("billing.read") else []
    open_msgs = await _open_support(db, 6) if can("support.read") else []
    flagged = await _flags(db, 6) if can("moderation.read") else []
    alerts = await _alerts(db) if can("system.read") else []
    return {
        "kpis": kpis,
        "charts": {"revenue": revenue, "signups": signups_s, "generations": gens_s,
                   "chars_by_plan": [{"plan": names.get(k, k), "value": v} for k, v in sorted(by_plan.items())],
                   "plan_mix": [{"plan": names.get(k, k), "value": v} for k, v in sorted(mix.items())]},
        "lists": {"signups": latest_signups, "payments": latest_payments, "support": open_msgs, "flagged": flagged,
                  "alerts": alerts},
    }


async def _open_support(db, limit):
    try:
        from models import Ticket
    except ImportError:
        rows = (await db.execute(select(ContactMessage).where(ContactMessage.handled.is_(False))
                                 .order_by(ContactMessage.id.desc()).limit(limit))).scalars()
        return [{"id": m.id, "subject": m.subject, "from": m.email, "created_at": iso(m.created_at), "to": "/admin/support"} for m in rows]
    rows = (await db.execute(select(Ticket).where(Ticket.status.in_(("new", "open"))).order_by(Ticket.id.desc()).limit(limit))).scalars()
    return [{"id": t.id, "subject": t.subject, "from": t.email, "created_at": iso(t.created_at), "kind": t.kind,
             "to": f"/admin/support/{t.id}"} for t in rows]


async def _flags(db, limit):
    try:
        from models import Flag
    except ImportError:
        return []
    rows = (await db.execute(select(Flag).where(Flag.status == "open").order_by(Flag.id.desc()).limit(limit))).scalars()
    return [{"id": f.id, "rule": f.rule_name, "severity": f.severity, "user_id": f.user_id, "created_at": iso(f.created_at),
             "to": "/admin/moderation"} for f in rows]


async def _alerts(db):
    try:
        from admin.health import active_alerts
    except ImportError:
        return []
    return await active_alerts(db)


# ── Global search (⌘K) ───────────────────────────────────────────────────────
@router.get("/search")
async def search(q: str = Query(min_length=2, max_length=100), p: Principal = Depends(require_unlocked),
                 db: AsyncSession = Depends(get_db)):
    q = q.strip()
    out: list[dict] = []
    can = lambda perm: rbac.has(p.user.role, perm)  # noqa: E731
    if can("users.read"):
        conds = [User.email.contains(q.lower())]
        if q.isdigit():
            conds.append(User.id == int(q))
        for u in (await db.execute(select(User).where(or_(*conds)).order_by(User.id.desc()).limit(8))).scalars():
            out.append({"type": "user", "id": str(u.id), "label": u.email, "sub": f"#{u.id} · {u.effective_plan}",
                        "to": f"/admin/users/{u.id}"})
    if can("billing.read"):
        if q.startswith("pay_") or len(q) >= 6:
            for x in (await db.execute(select(Payment).where(Payment.rzp_payment_id.contains(q)).limit(5))).scalars():
                out.append({"type": "payment", "id": x.rzp_payment_id, "label": x.rzp_payment_id,
                            "sub": f"₹{x.amount_paise / 100:,.2f} · {x.status}", "to": f"/admin/payments?q={x.rzp_payment_id}"})
        if q.startswith("sub_") or len(q) >= 6:
            for s in (await db.execute(select(Subscription).where(Subscription.rzp_subscription_id.contains(q)).limit(5))).scalars():
                out.append({"type": "subscription", "id": s.rzp_subscription_id, "label": s.rzp_subscription_id,
                            "sub": f"{s.plan} {s.period} · {s.status}", "to": f"/admin/subscriptions?q={s.rzp_subscription_id}"})
        if "/" in q or q.upper().startswith("AWZ"):
            for i in (await db.execute(select(Invoice).where(Invoice.number.contains(q.upper())).limit(5))).scalars():
                out.append({"type": "invoice", "id": i.number, "label": i.number, "sub": f"₹{i.total_paise / 100:,.2f} · {i.buyer_email}",
                            "to": f"/admin/invoices?q={i.number}"})
    return {"items": out[:20]}


# ── Notifications (bell) ─────────────────────────────────────────────────────
@router.get("/notifications")
async def notifications(p: Principal = Depends(require_unlocked), db: AsyncSession = Depends(get_db)):
    can = lambda perm: rbac.has(p.user.role, perm)  # noqa: E731
    now = utcnow()
    out: list[dict] = []
    if can("system.read"):
        for a in await _alerts(db):
            out.append({"id": f"alert-{a['key']}", "title": a["title"], "sub": a.get("detail"), "to": "/admin/health",
                        "level": a.get("level", "warning")})
    if can("support.read"):
        msgs = await _open_support(db, 50)
        if msgs:
            out.append({"id": "support", "title": f"{len(msgs)} open support message{'s' if len(msgs) != 1 else ''}",
                        "sub": msgs[0]["subject"], "to": "/admin/support", "level": "info"})
    if can("invites.read"):
        n = await _count(db, InviteRequest, InviteRequest.status == "new")
        if n:
            out.append({"id": "waitlist", "title": f"{n} new invite request{'s' if n != 1 else ''}", "to": "/admin/invites?tab=waitlist",
                        "level": "info"})
    if can("moderation.read"):
        flags = await _flags(db, 50)
        if flags:
            out.append({"id": "flags", "title": f"{len(flags)} flagged item{'s' if len(flags) != 1 else ''} to review",
                        "to": "/admin/moderation", "level": "warning"})
    if can("billing.read"):
        n = await _count(db, Payment, Payment.status == "failed", Payment.created_at >= now - timedelta(days=7))
        if n:
            out.append({"id": "failed-payments", "title": f"{n} failed payment{'s' if n != 1 else ''} (7 days)",
                        "to": "/admin/payments?status=failed", "level": "warning"})
    if can("queue.read"):
        n = await _count(db, Generation, Generation.status == "error", Generation.created_at >= now - timedelta(hours=24))
        if n:
            out.append({"id": "failed-jobs", "title": f"{n} failed job{'s' if n != 1 else ''} (24 h)", "to": "/admin/queue",
                        "level": "warning"})
    return {"items": out}

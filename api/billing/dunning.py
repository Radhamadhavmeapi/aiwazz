"""Dunning: a failed renewal opens a case. The user keeps paid access during the grace period (admin → Settings →
Billing, default 7 days), gets reminder emails on day 0, 3 and 7, and is moved to Free when the grace period ends
without a successful charge. Razorpay retries the charge itself; a later subscription.charged resolves the case."""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import DunningCase, Subscription, User

log = logging.getLogger("aiwazz.billing")
NOTICE_DAYS = (0, 3, 7)


async def _settings(db: AsyncSession) -> dict:
    from admin import settings_store
    return await settings_store.get(db, "billing")


async def open_case(db: AsyncSession, sub: Subscription, error: str) -> DunningCase:
    case = (await db.execute(select(DunningCase).where(DunningCase.subscription_id == sub.id, DunningCase.status == "open"))).scalars().first()
    if case is not None:
        case.failures += 1
        case.last_error = error[:255]
        return case
    cfg = await _settings(db)
    now = utcnow()
    case = DunningCase(subscription_id=sub.id, user_id=sub.user_id, started_at=now,
                       grace_until=now + timedelta(days=int(cfg["grace_days"])), last_error=error[:255])
    db.add(case)
    if sub.user_id:      # keep paid access during the grace period
        user = await db.get(User, sub.user_id)
        if user and user.plan == sub.plan and (user.plan_until is None or user.plan_until < case.grace_until):
            user.plan_until = case.grace_until if user.plan_until is not None else user.plan_until
    await db.flush()
    return case


async def resolve(db: AsyncSession, sub: Subscription) -> None:
    for case in (await db.execute(select(DunningCase).where(DunningCase.subscription_id == sub.id, DunningCase.status == "open"))).scalars():
        case.status, case.resolved_at = "resolved", utcnow()


async def run(db: AsyncSession) -> str:
    """Hourly: send due reminders, downgrade cases past their grace period. Idempotent."""
    from emails import send_template
    cfg = await _settings(db)
    now = utcnow()
    sent = downgraded = 0
    cases = (await db.execute(select(DunningCase).where(DunningCase.status == "open"))).scalars().all()
    for case in cases:
        sub = await db.get(Subscription, case.subscription_id)
        user = await db.get(User, case.user_id) if case.user_id else None
        if now >= case.grace_until:
            if user and sub and user.plan == sub.plan:
                user.plan, user.plan_until = "free", None
            case.status, case.resolved_at = "downgraded", now
            downgraded += 1
            continue
        if not (cfg.get("dunning_emails") and user and sub):
            continue
        day = (now - case.started_at).days
        done = {int(x) for x in case.emails_sent.split(",") if x}
        due = [d for d in NOTICE_DAYS if d <= day and d not in done]
        if due:
            key = "payment_failed" if 0 in due and not done else "dunning_reminder"
            await send_template(db, key, user.email, {"name": user.name or user.email.split("@")[0], "plan": sub.plan.title(),
                                "grace_until": f"{case.grace_until + timedelta(hours=5, minutes=30):%d %b %Y}"}, user_id=user.id)
            case.emails_sent = ",".join(str(x) for x in sorted(done | set(due)))
            sent += 1
    await db.commit()
    return f"{len(cases)} open, {sent} emails, {downgraded} downgraded"

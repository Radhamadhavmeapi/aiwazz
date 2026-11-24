"""Billing state changes, shared by the checkout callback and the webhook (the webhook is the source of truth).

A paid plan is just users.plan + users.plan_until: every successful charge sets plan_until = current_end + grace.
Cancelled, halted or completed subscriptions are never "downgraded" here: plan_until simply runs out and the
hourly sweep (usage.expire_plans) moves the user back to Free.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import Invoice, Payment, Subscription, User
from settings import get_settings

from . import invoice_pdf
from .gst import next_invoice_number, split_tax

log = logging.getLogger("aiwazz.billing")
LIVE = ("authenticated", "active", "pending")   # a subscription the user is (or is about to be) paying for


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(int(v), UTC).replace(tzinfo=None) if v else None


async def find_subscription(db: AsyncSession, rzp_id: str) -> Subscription | None:
    return (await db.execute(select(Subscription).where(Subscription.rzp_subscription_id == rzp_id))).scalar_one_or_none()


async def live_subscription(db: AsyncSession, user_id: int) -> Subscription | None:
    return (await db.execute(select(Subscription).where(Subscription.user_id == user_id, Subscription.status.in_(LIVE))
                             .order_by(Subscription.id.desc()))).scalars().first()


async def sync_subscription(db: AsyncSession, sub: Subscription, entity: dict) -> None:
    """Copy Razorpay's view of the subscription; extend the user's plan while it is active."""
    sub.status = entity.get("status", sub.status)
    sub.current_start = _ts(entity.get("current_start")) or sub.current_start
    sub.current_end = _ts(entity.get("current_end")) or sub.current_end
    sub.updated_at = utcnow()
    if sub.status in ("cancelled", "completed", "expired"):
        sub.cancel_at_period_end = False
    if sub.status == "active" and sub.user_id and sub.current_end:
        user = await db.get(User, sub.user_id)
        if user:
            until = sub.current_end + timedelta(days=get_settings().plan_grace_days)
            same = user.plan == sub.plan and user.plan_until is not None
            user.plan_until = max(until, user.plan_until) if same else until
            user.plan = sub.plan


async def record_charge(db: AsyncSession, sub: Subscription, payment: dict, sub_entity: dict) -> Invoice | None:
    """One Payment + one GST Invoice per captured payment (idempotent on the Razorpay payment id)."""
    pid = payment.get("id")
    if not pid or (await db.execute(select(Payment).where(Payment.rzp_payment_id == pid))).scalar_one_or_none():
        return None
    pay = Payment(user_id=sub.user_id, subscription_id=sub.id, rzp_payment_id=pid, amount_paise=int(payment.get("amount", 0)),
                  status=payment.get("status", "captured"), method=str(payment.get("method") or "")[:32])
    db.add(pay)
    await db.flush()
    user = await db.get(User, sub.user_id) if sub.user_id else None
    if user is None or pay.status not in ("captured", "authorized"):
        return None
    state = user.billing_state or "27"
    tax = split_tax(pay.amount_paise, state)
    now = utcnow()
    inv = Invoice(number=await next_invoice_number(db, now), user_id=user.id, payment_id=pay.id, issued_at=now,
                  plan=sub.plan, period=sub.period, period_start=_ts(sub_entity.get("current_start")) or sub.current_start,
                  period_end=_ts(sub_entity.get("current_end")) or sub.current_end,
                  buyer_name=user.billing_name or user.email, buyer_email=user.email, buyer_gstin=user.billing_gstin,
                  buyer_state=state, buyer_address=user.billing_address, taxable_paise=tax.taxable, cgst_paise=tax.cgst,
                  sgst_paise=tax.sgst, igst_paise=tax.igst, total_paise=tax.total)
    db.add(inv)
    await db.flush()
    return inv


def invoice_path(inv: Invoice):
    return get_settings().invoice_dir / f"{inv.number.replace('/', '-')}.pdf"


async def ensure_pdf(inv: Invoice):
    p = invoice_path(inv)
    if not p.exists():
        await asyncio.to_thread(invoice_pdf.render, inv, p)
    return p


async def handle_event(db: AsyncSession, event: str, payload: dict) -> str:
    """Apply one webhook event. Returns a short note for the log."""
    sub_entity = payload.get("subscription", {}).get("entity") or {}
    pay_entity = payload.get("payment", {}).get("entity") or {}
    rzp_sub = sub_entity.get("id") or pay_entity.get("subscription_id")
    if not rzp_sub:
        return "ignored (no subscription)"
    sub = await find_subscription(db, rzp_sub)
    if sub is None:
        return f"ignored (unknown subscription {rzp_sub})"
    if sub_entity:
        await sync_subscription(db, sub, sub_entity)
    inv = None
    if event == "subscription.charged" and pay_entity:
        inv = await record_charge(db, sub, pay_entity, sub_entity)
    await db.commit()
    if inv:
        await ensure_pdf(inv)
        from .emails import send_invoice_email
        await send_invoice_email(db, inv)
    return f"{event}: {sub.rzp_subscription_id} → {sub.status}" + (f", invoice {inv.number}" if inv else "")

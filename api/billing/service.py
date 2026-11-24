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


async def plan_id_for(db: AsyncSession, plan: str, period: str) -> str:
    """Razorpay plan id offered to NEW subscribers: the active plan version, else the ids from api/.env."""
    from models import PlanVersion
    v = (await db.execute(select(PlanVersion).where(PlanVersion.plan == plan, PlanVersion.period == period,
                                                    PlanVersion.active.is_(True), PlanVersion.rzp_plan_id != "")
                          .order_by(PlanVersion.id.desc()))).scalars().first()
    return v.rzp_plan_id if v else get_settings().razorpay_plan_ids.get(f"{plan}_{period}", "")


async def plan_for_rzp_id(db: AsyncSession, rzp_plan_id: str) -> tuple[str, str] | None:
    """(plan, period) of any version (current or grandfathered) of a Razorpay plan id."""
    from models import PlanVersion
    if not rzp_plan_id:
        return None
    v = (await db.execute(select(PlanVersion).where(PlanVersion.rzp_plan_id == rzp_plan_id))).scalars().first()
    if v:
        return v.plan, v.period
    for key, pid in get_settings().razorpay_plan_ids.items():
        if pid == rzp_plan_id and "_" in key:
            plan, period = key.split("_", 1)
            return plan, period
    return None


async def sync_subscription(db: AsyncSession, sub: Subscription, entity: dict) -> None:
    """Copy Razorpay's view of the subscription; extend the user's plan while it is active."""
    new_plan_id = entity.get("plan_id") or ""
    if new_plan_id and new_plan_id != sub.rzp_plan_id:
        mapped = await plan_for_rzp_id(db, new_plan_id)
        if mapped and sub.rzp_plan_id and mapped != (sub.plan, sub.period):
            log.info("subscription %s plan changed to %s/%s", sub.rzp_subscription_id, *mapped)
        if mapped:
            sub.plan, sub.period = mapped
            if (sub.pending_plan, sub.pending_period) == mapped:
                sub.pending_plan = sub.pending_period = None
        sub.rzp_plan_id = new_plan_id
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
    """Apply one webhook event (idempotent: replays change nothing twice). Returns a short note for the log."""
    from . import dunning
    if event.startswith("refund."):
        return await _refund_event(db, event, payload.get("refund", {}).get("entity") or {})
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
        await dunning.resolve(db, sub)
        await _redeem_coupon(db, sub)
    elif event == "payment.failed" and pay_entity:
        await record_failed_payment(db, sub, pay_entity)
        await dunning.open_case(db, sub, pay_entity.get("error_description") or "Payment failed")
    elif event in ("subscription.pending", "subscription.halted"):
        await dunning.open_case(db, sub, f"Subscription {sub.status}")
    elif event == "subscription.activated":
        await dunning.resolve(db, sub)
    await db.commit()
    if inv:
        await ensure_pdf(inv)
        from .emails import send_invoice_email
        await send_invoice_email(db, inv)
    return f"{event}: {sub.rzp_subscription_id} → {sub.status}" + (f", invoice {inv.number}" if inv else "")


async def record_failed_payment(db: AsyncSession, sub: Subscription, payment: dict) -> None:
    pid = payment.get("id")
    if not pid or (await db.execute(select(Payment).where(Payment.rzp_payment_id == pid))).scalar_one_or_none():
        return
    db.add(Payment(user_id=sub.user_id, subscription_id=sub.id, rzp_payment_id=pid, amount_paise=int(payment.get("amount", 0)),
                   status="failed", method=str(payment.get("method") or "")[:32],
                   error=str(payment.get("error_description") or payment.get("error_reason") or "")[:255]))
    await db.flush()


async def _redeem_coupon(db: AsyncSession, sub: Subscription) -> None:
    from models import CouponRedemption
    if sub.coupon_id:
        r = (await db.execute(select(CouponRedemption).where(CouponRedemption.subscription_id == sub.id,
                                                              CouponRedemption.status == "pending"))).scalars().first()
        if r:
            r.status = "redeemed"


async def _refund_event(db: AsyncSession, event: str, entity: dict) -> str:
    from models import Refund
    rid = entity.get("id")
    if not rid:
        return "ignored (no refund id)"
    ref = (await db.execute(select(Refund).where(Refund.rzp_refund_id == rid))).scalar_one_or_none()
    if ref is None:
        return f"ignored (unknown refund {rid})"
    status = "processed" if event == "refund.processed" else "failed" if event == "refund.failed" else ref.status
    await apply_refund_status(db, ref, status)
    await db.commit()
    return f"{event}: {rid} → {ref.status}"


async def apply_refund_status(db: AsyncSession, ref, status: str) -> None:
    """pending → processed: count it on the payment + issue the credit note (once). → failed: nothing is credited."""
    from .credit import issue_credit_note
    if ref.status == status or ref.status == "processed":
        return
    ref.status = status
    if status != "processed":
        return
    ref.processed_at = utcnow()
    pay = await db.get(Payment, ref.payment_id)
    pay.refunded_paise = (pay.refunded_paise or 0) + ref.amount_paise
    if pay.refunded_paise >= pay.amount_paise:
        pay.status = "refunded"
    inv = (await db.execute(select(Invoice).where(Invoice.payment_id == pay.id))).scalar_one_or_none()
    if inv is not None and ref.credit_note_id is None:
        await issue_credit_note(db, inv, ref.amount_paise, "refund", ref.reason, ref)


class PlanChangeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


RANK = {"starter": 1, "creator": 2, "pro": 3}


def is_upgrade(old_plan: str, old_period: str, new_plan: str, new_period: str) -> bool:
    """Higher tier = upgrade; same tier monthly → yearly = upgrade (paid now); everything else = downgrade."""
    if RANK.get(new_plan, 0) != RANK.get(old_plan, 0):
        return RANK.get(new_plan, 0) > RANK.get(old_plan, 0)
    return old_period == "monthly" and new_period == "yearly"


async def change_subscription_plan(db: AsyncSession, rz, sub: Subscription, plan: str, period: str) -> str:
    """Owner decision (24 Nov 2026): upgrades apply now with proration (Razorpay charges the difference), downgrades
    at the period end. Returns "now" or "period_end". Raises PlanChangeError with a user-facing message."""
    from .razorpay import RazorpayError
    if (plan, period) == (sub.plan, sub.period):
        if sub.pending_plan:
            sub.pending_plan = sub.pending_period = None   # cancel a scheduled downgrade by "changing" back
            return "now"
        raise PlanChangeError(422, "You're already on this plan")
    if sub.status != "active":
        raise PlanChangeError(409, "The plan can be changed once the subscription is active")
    plan_id = await plan_id_for(db, plan, period)
    if not plan_id:
        raise PlanChangeError(503, "This plan isn't available for online payment yet")
    now = is_upgrade(sub.plan, sub.period, plan, period)
    try:
        entity = await rz.update_subscription(sub.rzp_subscription_id, plan_id, now)
    except RazorpayError as e:
        log.warning("update_subscription failed: %s", e)
        raise PlanChangeError(502, f"Razorpay couldn't change the plan: {e}. Plan changes work for card payments; "
                                   "with UPI AutoPay, cancel and subscribe again.") from e
    if now:
        await sync_subscription(db, sub, entity | {"plan_id": plan_id})
        sub.pending_plan = sub.pending_period = None
    else:
        sub.pending_plan, sub.pending_period = plan, period
        sub.updated_at = utcnow()
    return "now" if now else "period_end"

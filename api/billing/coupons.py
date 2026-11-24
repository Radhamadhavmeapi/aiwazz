"""Coupon validation. How a discount is applied (documented choice, A3): Razorpay Subscriptions take an `offer_id`
when the subscription is created; offers can only be created in the Razorpay Dashboard (no API). So staff create the
offer there, paste its id on the coupon, and we validate the code here (plan, period, dates, total and per-user
limits) before passing the offer_id. Razorpay applies the discount (first payment or N cycles, as configured on the
offer); the GST invoice is worked back from the amount actually paid, so it is always correct."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import Coupon, CouponRedemption

INVALID = "This code isn't valid"


def normalize(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum() or c in "-_")[:32]


async def check_coupon(db: AsyncSession, code: str, user_id: int, plan: str, period: str) -> Coupon:
    c = (await db.execute(select(Coupon).where(Coupon.code == normalize(code)))).scalar_one_or_none()
    now = utcnow()
    if c is None or not c.active or (c.starts_at and c.starts_at > now) or (c.ends_at and c.ends_at <= now):
        raise HTTPException(422, INVALID)
    if c.plans and plan not in c.plans.split(","):
        raise HTTPException(422, "This code isn't valid for this plan")
    if period not in c.periods.split(","):
        raise HTTPException(422, f"This code isn't valid for {period} billing")
    if not c.rzp_offer_id:
        raise HTTPException(422, "This code can't be used for online payment yet")
    used = (await db.execute(select(func.count()).select_from(CouponRedemption).where(
        CouponRedemption.coupon_id == c.id, CouponRedemption.status != "void"))).scalar_one()
    if c.max_redemptions is not None and used >= c.max_redemptions:
        raise HTTPException(422, "This code has been fully used")
    mine = (await db.execute(select(func.count()).select_from(CouponRedemption).where(
        CouponRedemption.coupon_id == c.id, CouponRedemption.user_id == user_id, CouponRedemption.status == "redeemed"))).scalar_one()
    if mine >= c.per_user_limit:
        raise HTTPException(422, "You've already used this code")
    return c


def describe(c: Coupon) -> str:
    off = f"{c.value}% off" if c.kind == "percent" else f"₹{c.value / 100:,.0f} off"
    return off + (" the first payment" if c.duration == "once" else f" for {c.cycles} billing cycles")

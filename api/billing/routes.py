"""/api/billing: plans, billing details, Razorpay subscription checkout, cancel, invoices, webhook."""
import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import ratelimit
from auth.deps import Principal, csrf_protect, current_principal
from db import get_db, utcnow
from models import Invoice, Subscription, User, WebhookEvent
from settings import get_settings

from . import service
from .gst import GST_RATE, PAID_PLANS, PERIODS, STATES, charge_paise, gstin_problem, plan_prices
from .razorpay import RazorpayError, checkout_signature_ok, client, webhook_signature_ok

log = logging.getLogger("aiwazz.billing")
router = APIRouter(prefix="/api/billing", tags=["billing"])
ORDER = {p: i for i, p in enumerate(("free",) + PAID_PLANS)}


async def _session_user(p: Principal = Depends(current_principal)) -> Principal:
    if p.via != "session":
        raise HTTPException(403, "Billing is only available in the dashboard")
    return p


def _iso(d):
    return d.isoformat() + "Z" if d else None


def _sub_out(s: Subscription | None) -> dict | None:
    if s is None:
        return None
    return {"id": s.id, "plan": s.plan, "period": s.period, "status": s.status, "current_start": _iso(s.current_start),
            "current_end": _iso(s.current_end), "cancel_at_period_end": s.cancel_at_period_end}


def _profile(u: User) -> dict:
    return {"name": u.billing_name, "gstin": u.billing_gstin, "state": u.billing_state, "address": u.billing_address}


@router.get("")
async def billing_overview(p: Principal = Depends(_session_user), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    user = await db.get(User, p.user.id)
    sub = await service.live_subscription(db, user.id)
    if sub is None:   # show a cancelled plan that still runs until its period end
        sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "cancelled",
                                                           Subscription.current_end > utcnow())
                                .order_by(Subscription.id.desc()))).scalars().first()
    invoices = (await db.execute(select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.id.desc()).limit(36))).scalars().all()
    prices = plan_prices()
    return {
        "enabled": s.billing_enabled, "test_mode": s.billing_test_mode, "gst_rate": GST_RATE,
        "plans": [{"id": k, **v, "total_monthly_paise": charge_paise(k, "monthly")[1],
                   "total_yearly_paise": charge_paise(k, "yearly")[1]} for k, v in prices.items()],
        "subscription": _sub_out(sub), "profile": _profile(user),
        "invoices": [{"id": i.id, "number": i.number, "issued_at": _iso(i.issued_at), "plan": i.plan, "period": i.period,
                      "total_paise": i.total_paise} for i in invoices],
        "states": [{"code": c, "name": n} for c, n in sorted(STATES.items(), key=lambda x: x[1])],
    }


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    gstin: str = Field(default="", max_length=15)
    state: str = Field(min_length=2, max_length=2)
    address: str = Field(default="", max_length=300)


@router.put("/profile", dependencies=[Depends(csrf_protect)])
async def save_profile(body: ProfileIn, p: Principal = Depends(_session_user), db: AsyncSession = Depends(get_db)):
    if body.state not in STATES:
        raise HTTPException(422, "Pick your state")
    gstin = body.gstin.strip().upper()
    if gstin and (msg := gstin_problem(gstin, body.state)):
        raise HTTPException(422, msg)
    if gstin and not body.address.strip():
        raise HTTPException(422, "Add your business address (needed on a GST invoice with a GSTIN)")
    user = await db.get(User, p.user.id)
    user.billing_name, user.billing_gstin = body.name.strip(), gstin
    user.billing_state, user.billing_address = body.state, body.address.strip()
    await db.commit()
    return _profile(user)


class SubscribeIn(BaseModel):
    plan: str
    period: str


@router.post("/subscribe", dependencies=[Depends(csrf_protect)])
async def subscribe(body: SubscribeIn, request: Request, p: Principal = Depends(_session_user), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    if not s.billing_enabled:
        raise HTTPException(503, "Online payments aren't open yet")
    if body.plan not in PAID_PLANS or body.period not in PERIODS:
        raise HTTPException(422, "Unknown plan")
    plan_id = s.razorpay_plan_ids.get(f"{body.plan}_{body.period}")
    if not plan_id:
        raise HTTPException(503, "This plan isn't available for online payment yet")
    user = await db.get(User, p.user.id)
    if not (user.billing_name and user.billing_state):
        raise HTTPException(422, "Add your billing details first (name and state, for the GST invoice)")
    if (live := await service.live_subscription(db, user.id)) is not None:
        raise HTTPException(409, f"You already have the {live.plan.title()} plan. Cancel it first; you can pick a new plan "
                                 "when it ends, or contact support to switch now.")
    lim = await ratelimit.hit(request.app.state.redis, s.redis_prefix, f"subscribe:user:{user.id}", 10, 3600)
    if not lim.allowed:
        raise HTTPException(429, "Too many checkout attempts. Try again later.")
    try:
        # total_count: how many renewals Razorpay may charge (10 years); the user can cancel any time.
        rs = await client().create_subscription(plan_id, 120 if body.period == "monthly" else 10,
                                                {"user_id": str(user.id), "plan": body.plan, "period": body.period})
    except RazorpayError as e:
        log.warning("create_subscription failed: %s", e)
        raise HTTPException(502, "Couldn't start the payment. Please try again.") from e
    db.add(Subscription(user_id=user.id, rzp_subscription_id=rs["id"], plan=body.plan, period=body.period,
                        status=rs.get("status", "created")))
    await db.commit()
    price = plan_prices()[body.plan]
    return {"key_id": s.razorpay_key_id, "subscription_id": rs["id"], "name": "AiWazz",
            "description": f"{price['name']} plan ({body.period}) + {GST_RATE}% GST",
            "amount_paise": charge_paise(body.plan, body.period)[1],
            "prefill": {"email": user.email, "name": user.billing_name}}


class VerifyIn(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@router.post("/verify", dependencies=[Depends(csrf_protect)])
async def verify(body: VerifyIn, p: Principal = Depends(_session_user), db: AsyncSession = Depends(get_db)):
    """Checkout success callback. Confirms the signature, then reads the subscription from Razorpay (not from the browser)."""
    sub = await service.find_subscription(db, body.razorpay_subscription_id)
    if sub is None or sub.user_id != p.user.id:
        raise HTTPException(404, "Not found")
    if not checkout_signature_ok(body.razorpay_payment_id, body.razorpay_subscription_id, body.razorpay_signature):
        raise HTTPException(400, "Payment signature check failed")
    try:
        await service.sync_subscription(db, sub, await client().get_subscription(sub.rzp_subscription_id))
    except RazorpayError as e:
        log.warning("get_subscription failed: %s", e)   # the webhook will catch up
    await db.commit()
    return {"subscription": _sub_out(sub)}


@router.post("/cancel", dependencies=[Depends(csrf_protect)])
async def cancel(p: Principal = Depends(_session_user), db: AsyncSession = Depends(get_db)):
    sub = await service.live_subscription(db, p.user.id)
    if sub is None:
        raise HTTPException(404, "You don't have a plan to cancel")
    try:
        entity = await client().cancel_subscription(sub.rzp_subscription_id, at_cycle_end=sub.status == "active")
    except RazorpayError as e:
        log.warning("cancel failed: %s", e)
        raise HTTPException(502, "Couldn't cancel right now. Please try again in a minute.") from e
    await service.sync_subscription(db, sub, entity)
    if sub.status == "active":       # cancelled at cycle end: still active until current_end
        sub.cancel_at_period_end = True
    await db.commit()
    return {"subscription": _sub_out(sub)}


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: int, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    inv = await db.get(Invoice, invoice_id)
    if inv is None or (inv.user_id != p.user.id and not p.user.is_admin):
        raise HTTPException(404, "Not found")
    path = await service.ensure_pdf(inv)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Razorpay → us. Authenticated only by the HMAC signature; each event id is processed once."""
    raw = await request.body()
    if not webhook_signature_ok(raw, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(400, "Bad signature")
    data = json.loads(raw)
    event = data.get("event", "")
    event_id = request.headers.get("x-razorpay-event-id") or "sha256:" + hashlib.sha256(raw).hexdigest()[:56]
    db.add(WebhookEvent(id=event_id[:64], event=event[:64]))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"ok": True, "duplicate": True}
    note = await service.handle_event(db, event, data.get("payload", {}))
    await db.commit()
    log.info("webhook %s", note)
    return {"ok": True}


async def cancel_for_account_deletion(db: AsyncSession, user_id: int) -> None:
    """Stop future charges immediately when an account is deleted (raises HTTPException if Razorpay can't be reached)."""
    sub = await service.live_subscription(db, user_id)
    if sub is None:
        return
    try:
        entity = await client().cancel_subscription(sub.rzp_subscription_id, at_cycle_end=False)
    except RazorpayError as e:
        raise HTTPException(502, "Couldn't cancel your plan with our payment provider. Please try again in a minute.") from e
    await service.sync_subscription(db, sub, entity)

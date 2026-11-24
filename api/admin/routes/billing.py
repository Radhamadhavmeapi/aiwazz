"""A3: billing back office — subscriptions (cancel, pause/resume, change plan, sync), payments + refunds (credit note
on processing), invoices + credit notes (PDF, regenerate, void), dunning, webhooks log + replay, GST reports."""
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from billing import routes as broutes
from billing import service
from billing.gst import STATES, financial_year
from billing.razorpay import RazorpayError
from db import get_db, utcnow
from models import (CreditNote, DunningCase, Invoice, Payment, Refund, Subscription, User, WebhookEvent)
from settings import get_settings

from .. import settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, csv_response, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
IST = timedelta(hours=5, minutes=30)
RZP_DASH = "https://dashboard.razorpay.com/app"


def _rzp_error(e: RazorpayError) -> HTTPException:
    return HTTPException(502, f"Razorpay: {e}")


async def _emails(db, ids) -> dict[int, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.email).where(User.id.in_(ids)))).all())


# ── Subscriptions ────────────────────────────────────────────────────────────
def _sub_row(s: Subscription, email: str = "") -> dict:
    next_charge = s.current_end if s.status == "active" and not s.cancel_at_period_end else None
    return {"id": s.id, "rzp_subscription_id": s.rzp_subscription_id, "user_id": s.user_id, "email": email, "plan": s.plan,
            "period": s.period, "status": s.status, "current_start": iso(s.current_start), "current_end": iso(s.current_end),
            "next_charge_at": iso(next_charge), "cancel_at_period_end": s.cancel_at_period_end,
            "pending_plan": s.pending_plan, "pending_period": s.pending_period, "created_at": iso(s.created_at),
            "dashboard_url": f"{RZP_DASH}/subscriptions/{s.rzp_subscription_id}"}


@router.get("/subscriptions")
async def list_subscriptions(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                             plan: str = Query("", max_length=16), period: str = Query("", max_length=8),
                             p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(Subscription, User.email).outerjoin(User, User.id == Subscription.user_id)
    if status:
        stmt = stmt.where(Subscription.status == status)
    if plan:
        stmt = stmt.where(Subscription.plan == plan)
    if period:
        stmt = stmt.where(Subscription.period == period)
    if lp.q:
        stmt = stmt.where(or_(Subscription.rzp_subscription_id.contains(lp.q), User.email.contains(lp.q.lower())))
    return await respond(db, request, p, stmt, lp, scalars=False, name="subscriptions",
                         sorts={"created_at": Subscription.created_at, "current_end": Subscription.current_end},
                         default_sort=Subscription.id.desc(), row=lambda r: _sub_row(r[0], r[1] or ""))


async def _get_sub(db, sid) -> Subscription:
    s = await db.get(Subscription, sid)
    if s is None:
        raise HTTPException(404, "Subscription not found")
    return s


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class CancelIn(ReasonIn):
    at_period_end: bool = True


@router.post("/subscriptions/{sid}/cancel")
async def cancel_subscription(sid: int, body: CancelIn, request: Request, p: Principal = Depends(require_perm("billing.write")),
                              _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    sub = await _get_sub(db, sid)
    if sub.status not in service.LIVE + ("halted", "paused"):
        raise HTTPException(409, f"This subscription is already {sub.status}")
    before = _sub_row(sub)
    at_end = body.at_period_end and sub.status == "active"
    try:
        entity = await broutes.client().cancel_subscription(sub.rzp_subscription_id, at_cycle_end=at_end)
    except RazorpayError as e:
        raise _rzp_error(e) from e
    await service.sync_subscription(db, sub, entity)
    if at_end and sub.status == "active":
        sub.cancel_at_period_end = True
    elif sub.user_id and not at_end:       # cancel now: paid access ends now
        user = await db.get(User, sub.user_id)
        if user and user.plan == sub.plan:
            user.plan, user.plan_until = "free", None
    audit(db, request, p.user, "billing.subscription.cancel", target_type="subscription", target_id=sub.id,
          label=sub.rzp_subscription_id, before=before, after=_sub_row(sub), reason=body.reason)
    await db.commit()
    return _sub_row(sub)


class PauseIn(ReasonIn):
    pause: bool


@router.post("/subscriptions/{sid}/pause")
async def pause_subscription(sid: int, body: PauseIn, request: Request, p: Principal = Depends(require_perm("billing.write")),
                             db: AsyncSession = Depends(get_db)):
    sub = await _get_sub(db, sid)
    before = _sub_row(sub)
    try:
        rz = broutes.client()
        entity = await (rz.pause_subscription if body.pause else rz.resume_subscription)(sub.rzp_subscription_id)
    except RazorpayError as e:
        raise _rzp_error(e) from e
    await service.sync_subscription(db, sub, entity)
    audit(db, request, p.user, "billing.subscription.pause" if body.pause else "billing.subscription.resume",
          target_type="subscription", target_id=sub.id, label=sub.rzp_subscription_id, before=before, after=_sub_row(sub),
          reason=body.reason)
    await db.commit()
    return _sub_row(sub)


class ChangeIn(ReasonIn):
    plan: str = Field(pattern="^(starter|creator|pro)$")
    period: str = Field(pattern="^(monthly|yearly)$")


@router.post("/subscriptions/{sid}/change-plan")
async def change_subscription_plan(sid: int, body: ChangeIn, request: Request, p: Principal = Depends(require_perm("billing.write")),
                                   _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    sub = await _get_sub(db, sid)
    before = _sub_row(sub)
    try:
        when = await service.change_subscription_plan(db, broutes.client(), sub, body.plan, body.period)
    except service.PlanChangeError as e:
        raise HTTPException(e.status, str(e)) from e
    audit(db, request, p.user, "billing.subscription.change_plan", target_type="subscription", target_id=sub.id,
          label=sub.rzp_subscription_id, before=before, after=_sub_row(sub) | {"applies": when}, reason=body.reason)
    await db.commit()
    return _sub_row(sub) | {"applies": when}


@router.post("/subscriptions/{sid}/sync")
async def sync_subscription(sid: int, request: Request, p: Principal = Depends(require_perm("billing.write")),
                            db: AsyncSession = Depends(get_db)):
    sub = await _get_sub(db, sid)
    try:
        await service.sync_subscription(db, sub, await broutes.client().get_subscription(sub.rzp_subscription_id))
    except RazorpayError as e:
        raise _rzp_error(e) from e
    audit(db, request, p.user, "billing.subscription.sync", target_type="subscription", target_id=sub.id, label=sub.rzp_subscription_id)
    await db.commit()
    return _sub_row(sub)


# ── Payments + refunds ───────────────────────────────────────────────────────
def _pay_row(x: Payment, email: str = "", inv: Invoice | None = None) -> dict:
    return {"id": x.id, "rzp_payment_id": x.rzp_payment_id, "user_id": x.user_id, "email": email, "amount_paise": x.amount_paise,
            "status": x.status, "method": x.method, "error": x.error, "refunded_paise": x.refunded_paise or 0,
            "created_at": iso(x.created_at), "dashboard_url": f"{RZP_DASH}/payments/{x.rzp_payment_id}",
            "invoice": {"id": inv.id, "number": inv.number, "taxable_paise": inv.taxable_paise, "cgst_paise": inv.cgst_paise,
                        "sgst_paise": inv.sgst_paise, "igst_paise": inv.igst_paise} if inv else None}


@router.get("/payments")
async def list_payments(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                        method: str = Query("", max_length=32), p: Principal = Depends(require_perm("billing.read")),
                        db: AsyncSession = Depends(get_db)):
    stmt = select(Payment, User.email, Invoice).outerjoin(User, User.id == Payment.user_id).outerjoin(Invoice, Invoice.payment_id == Payment.id)
    if status:
        stmt = stmt.where(Payment.status == status)
    if method:
        stmt = stmt.where(Payment.method == method)
    if lp.q:
        stmt = stmt.where(or_(Payment.rzp_payment_id.contains(lp.q), User.email.contains(lp.q.lower()), Invoice.number.contains(lp.q.upper())))

    def csv_row(r):
        x, email, inv = r
        return {"payment_id": x.rzp_payment_id, "date_ist": f"{x.created_at + IST:%Y-%m-%d %H:%M}", "email": email or "",
                "amount_inr": x.amount_paise / 100, "status": x.status, "method": x.method, "refunded_inr": (x.refunded_paise or 0) / 100,
                "invoice": inv.number if inv else "", "taxable_inr": inv.taxable_paise / 100 if inv else "",
                "cgst_inr": inv.cgst_paise / 100 if inv else "", "sgst_inr": inv.sgst_paise / 100 if inv else "",
                "igst_inr": inv.igst_paise / 100 if inv else "", "error": x.error}
    return await respond(db, request, p, stmt, lp, scalars=False, name="payments", csv_row=csv_row,
                         sorts={"created_at": Payment.created_at, "amount": Payment.amount_paise},
                         default_sort=Payment.id.desc(), row=lambda r: _pay_row(r[0], r[1] or "", r[2]))


class RefundIn(ReasonIn):
    amount_paise: int | None = Field(default=None, ge=1)     # None = full (what's left)


@router.post("/payments/{pid}/refund")
async def refund_payment(pid: int, body: RefundIn, request: Request, p: Principal = Depends(require_perm("billing.refund")),
                         _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    pay = await db.get(Payment, pid)
    if pay is None:
        raise HTTPException(404, "Payment not found")
    if pay.status not in ("captured", "refunded"):
        raise HTTPException(409, f"Only captured payments can be refunded (this one is {pay.status})")
    pending = (await db.execute(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
        Refund.payment_id == pay.id, Refund.status == "pending"))).scalar_one()
    left = pay.amount_paise - (pay.refunded_paise or 0) - int(pending)
    amount = body.amount_paise or left
    if left <= 0:
        raise HTTPException(409, "This payment is already fully refunded")
    if amount > left:
        raise HTTPException(422, f"At most ₹{left / 100:,.2f} can still be refunded")
    try:
        entity = await broutes.client().refund_payment(pay.rzp_payment_id, amount, {"reason": body.reason[:200], "by": p.user.email})
    except RazorpayError as e:
        raise _rzp_error(e) from e
    ref = Refund(rzp_refund_id=entity.get("id"), payment_id=pay.id, user_id=pay.user_id, amount_paise=amount,
                 reason=body.reason, status="pending", created_by=p.user.id)
    db.add(ref)
    await db.flush()
    if entity.get("status") == "processed":
        await service.apply_refund_status(db, ref, "processed")
    audit(db, request, p.user, "billing.refund", target_type="payment", target_id=pay.id, label=pay.rzp_payment_id,
          after={"amount_paise": amount, "rzp_refund_id": ref.rzp_refund_id, "status": ref.status}, reason=body.reason, full=True)
    await db.commit()
    return {"refund": _refund_row(ref)}


def _refund_row(r: Refund, email: str = "") -> dict:
    return {"id": r.id, "rzp_refund_id": r.rzp_refund_id, "payment_id": r.payment_id, "user_id": r.user_id, "email": email,
            "amount_paise": r.amount_paise, "reason": r.reason, "status": r.status, "created_at": iso(r.created_at),
            "processed_at": iso(r.processed_at), "credit_note_id": r.credit_note_id}


@router.get("/refunds")
async def list_refunds(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("billing.read")),
                       db: AsyncSession = Depends(get_db)):
    stmt = select(Refund, User.email).outerjoin(User, User.id == Refund.user_id)
    return await respond(db, request, p, stmt, lp, scalars=False, name="refunds", sorts={"created_at": Refund.created_at},
                         default_sort=Refund.id.desc(), row=lambda r: _refund_row(r[0], r[1] or ""))


# ── Invoices + credit notes ──────────────────────────────────────────────────
def _inv_row(i: Invoice) -> dict:
    return {"id": i.id, "number": i.number, "issued_at": iso(i.issued_at), "user_id": i.user_id, "buyer_name": i.buyer_name,
            "buyer_email": i.buyer_email, "buyer_gstin": i.buyer_gstin, "buyer_state": i.buyer_state, "plan": i.plan,
            "period": i.period, "taxable_paise": i.taxable_paise, "cgst_paise": i.cgst_paise, "sgst_paise": i.sgst_paise,
            "igst_paise": i.igst_paise, "total_paise": i.total_paise, "voided_at": iso(i.voided_at),
            "type": "B2B" if i.buyer_gstin else "B2C"}


def _month_range(month: str) -> tuple[datetime, datetime]:
    try:
        y, m = (int(x) for x in month.split("-"))
        start = datetime(y, m, 1)
    except ValueError as e:
        raise HTTPException(422, "Month looks like 2026-11") from e
    end = datetime(y + (m == 12), m % 12 + 1, 1)
    return start - IST, end - IST


@router.get("/invoices")
async def list_invoices(request: Request, lp: ListParams = Depends(), month: str = Query("", max_length=7),
                        type: str = Query("", pattern="^(|B2B|B2C)$"), p: Principal = Depends(require_perm("billing.read")),
                        db: AsyncSession = Depends(get_db)):
    stmt = select(Invoice)
    if month:
        a, b = _month_range(month)
        stmt = stmt.where(Invoice.issued_at >= a, Invoice.issued_at < b)
    if type == "B2B":
        stmt = stmt.where(Invoice.buyer_gstin != "")
    elif type == "B2C":
        stmt = stmt.where(Invoice.buyer_gstin == "")
    if lp.q:
        stmt = stmt.where(or_(Invoice.number.contains(lp.q.upper()), Invoice.buyer_email.contains(lp.q.lower()),
                              Invoice.buyer_name.contains(lp.q)))
    return await respond(db, request, p, stmt, lp, sorts={"issued_at": Invoice.issued_at, "total": Invoice.total_paise},
                         default_sort=Invoice.id.desc(), row=_inv_row, name="invoices")


def _cn_row(c: CreditNote, inv_number: str = "") -> dict:
    return {"id": c.id, "number": c.number, "invoice_id": c.invoice_id, "invoice_number": inv_number, "kind": c.kind,
            "reason": c.reason, "issued_at": iso(c.issued_at), "taxable_paise": c.taxable_paise, "cgst_paise": c.cgst_paise,
            "sgst_paise": c.sgst_paise, "igst_paise": c.igst_paise, "total_paise": c.total_paise}


@router.get("/credit-notes")
async def list_credit_notes(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("billing.read")),
                            db: AsyncSession = Depends(get_db)):
    stmt = select(CreditNote, Invoice.number).join(Invoice, Invoice.id == CreditNote.invoice_id)
    if lp.q:
        stmt = stmt.where(or_(CreditNote.number.contains(lp.q.upper()), Invoice.number.contains(lp.q.upper())))
    return await respond(db, request, p, stmt, lp, scalars=False, name="credit-notes", sorts={"issued_at": CreditNote.issued_at},
                         default_sort=CreditNote.id.desc(), row=lambda r: _cn_row(r[0], r[1]))


async def _get_inv(db, iid) -> Invoice:
    inv = await db.get(Invoice, iid)
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.get("/invoices/{iid}/pdf")
async def invoice_pdf(iid: int, p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    path = await service.ensure_pdf(await _get_inv(db, iid))
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/credit-notes/{cid}/pdf")
async def credit_note_pdf(cid: int, p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    from billing.credit import ensure_credit_note_pdf
    cn = await db.get(CreditNote, cid)
    if cn is None:
        raise HTTPException(404, "Credit note not found")
    path = await ensure_credit_note_pdf(db, cn)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/invoices/{iid}/regenerate")
async def regenerate_invoice(iid: int, request: Request, p: Principal = Depends(require_perm("billing.write")),
                             db: AsyncSession = Depends(get_db)):
    """Re-render the PDF from the stored invoice (same number and amounts; e.g. after a layout fix)."""
    inv = await _get_inv(db, iid)
    service.invoice_path(inv).unlink(missing_ok=True)
    await service.ensure_pdf(inv)
    audit(db, request, p.user, "billing.invoice.regenerate", target_type="invoice", target_id=inv.id, label=inv.number)
    await db.commit()
    return {"ok": True}


@router.post("/invoices/{iid}/void")
async def void_invoice(iid: int, body: ReasonIn, request: Request, p: Principal = Depends(require_perm("billing.write")),
                       _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    """Cancel an invoice with a credit note for whatever hasn't been credited yet. The invoice keeps its number."""
    from billing.credit import credited_paise, ensure_credit_note_pdf, issue_credit_note
    inv = await _get_inv(db, iid)
    if inv.voided_at:
        raise HTTPException(409, "This invoice is already void")
    left = inv.total_paise - await credited_paise(db, inv.id)
    cn = await issue_credit_note(db, inv, left, "void", body.reason) if left > 0 else None
    inv.voided_at = utcnow()
    audit(db, request, p.user, "billing.invoice.void", target_type="invoice", target_id=inv.id, label=inv.number,
          after={"credit_note": cn.number if cn else None, "credited_paise": left}, reason=body.reason, full=True)
    await db.commit()
    if cn:
        await ensure_credit_note_pdf(db, cn)
    return {"ok": True, "credit_note": _cn_row(cn, inv.number) if cn else None}


# ── Dunning ──────────────────────────────────────────────────────────────────
@router.get("/dunning")
async def list_dunning(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                       p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(DunningCase, User.email, Subscription).outerjoin(User, User.id == DunningCase.user_id) \
        .join(Subscription, Subscription.id == DunningCase.subscription_id)
    if status:
        stmt = stmt.where(DunningCase.status == status)

    def row(r):
        c, email, s = r
        return {"id": c.id, "email": email or "", "user_id": c.user_id, "subscription": s.rzp_subscription_id, "plan": s.plan,
                "sub_status": s.status, "started_at": iso(c.started_at), "grace_until": iso(c.grace_until), "failures": c.failures,
                "last_error": c.last_error, "emails_sent": [int(x) for x in c.emails_sent.split(",") if x], "status": c.status,
                "resolved_at": iso(c.resolved_at)}
    return await respond(db, request, p, stmt, lp, scalars=False, name="dunning", sorts={"started_at": DunningCase.started_at},
                         default_sort=DunningCase.id.desc(), row=row)


class BillingSettingsIn(BaseModel):
    grace_days: int = Field(ge=0, le=30)
    dunning_emails: bool = True


@router.get("/settings/billing")
async def get_billing_settings(p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    return {**await settings_store.get(db, "billing"), "mode": "OFF" if not s.razorpay_key_id else ("TEST" if s.billing_test_mode else "LIVE"),
            "keys_set": bool(s.razorpay_key_id and s.razorpay_key_secret), "webhook_secret_set": bool(s.razorpay_webhook_secret)}


@router.put("/settings/billing")
async def put_billing_settings(body: BillingSettingsIn, request: Request, p: Principal = Depends(require_perm("billing.write")),
                               _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "billing")
    after = {**before, **body.model_dump()}
    await settings_store.put(db, "billing", after, p.user.id)
    audit(db, request, p.user, "settings.billing", target_type="setting", target_id="billing", before=before, after=after)
    await db.commit()
    return after


# ── Webhooks log ─────────────────────────────────────────────────────────────
def _wh_row(w: WebhookEvent) -> dict:
    return {"id": w.id, "event": w.event, "received_at": iso(w.received_at), "signature_ok": w.signature_ok, "status": w.status,
            "note": w.note, "replays": w.replays}


@router.get("/webhooks")
async def list_webhooks(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                        p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(WebhookEvent)
    if status:
        stmt = stmt.where(WebhookEvent.status == status)
    if lp.q:
        stmt = stmt.where(or_(WebhookEvent.event.contains(lp.q), WebhookEvent.id.contains(lp.q), WebhookEvent.note.contains(lp.q)))
    return await respond(db, request, p, stmt, lp, sorts={"received_at": WebhookEvent.received_at},
                         default_sort=WebhookEvent.received_at.desc(), row=_wh_row, name="webhooks")


@router.get("/webhooks/{eid}")
async def webhook_detail(eid: str, p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    w = await db.get(WebhookEvent, eid)
    if w is None:
        raise HTTPException(404, "Event not found")
    return _wh_row(w) | {"payload": w.payload}


@router.post("/webhooks/{eid}/replay")
async def replay_webhook(eid: str, request: Request, p: Principal = Depends(require_perm("billing.write")),
                         db: AsyncSession = Depends(get_db)):
    """Re-run a stored event (signature was verified when it arrived). Idempotent: payments, invoices and credit notes
    are keyed on Razorpay ids, so a replay never duplicates them."""
    import json
    w = await db.get(WebhookEvent, eid)
    if w is None:
        raise HTTPException(404, "Event not found")
    if not w.signature_ok or not w.payload:
        raise HTTPException(409, "Only events with a valid signature can be replayed")
    w.replays += 1
    audit(db, request, p.user, "billing.webhook.replay", target_type="webhook", target_id=w.id, label=w.event)
    await db.commit()
    try:
        await broutes.process_event(db, w, json.loads(w.payload))
    except HTTPException:
        pass
    w = await db.get(WebhookEvent, eid)
    return _wh_row(w)


# ── GST reports (for the CA) ─────────────────────────────────────────────────
async def gst_report(db: AsyncSession, month: str) -> dict:
    a, b = _month_range(month)
    invs = (await db.execute(select(Invoice).where(Invoice.issued_at >= a, Invoice.issued_at < b).order_by(Invoice.number))).scalars().all()
    cns = (await db.execute(select(CreditNote, Invoice).join(Invoice, Invoice.id == CreditNote.invoice_id)
                            .where(CreditNote.issued_at >= a, CreditNote.issued_at < b).order_by(CreditNote.number))).all()
    pays = (await db.execute(select(Payment, Invoice.number).outerjoin(Invoice, Invoice.payment_id == Payment.id)
                             .where(Payment.created_at >= a, Payment.created_at < b).order_by(Payment.created_at))).all()
    r = lambda paise: round(paise / 100, 2)  # noqa: E731
    from billing.gst import LEGAL
    sac = LEGAL.get("sacCode", "998439")
    register = [{"invoice_no": i.number, "date": f"{i.issued_at + IST:%d-%m-%Y}", "buyer": i.buyer_name, "buyer_gstin": i.buyer_gstin,
                 "type": "B2B" if i.buyer_gstin else "B2C", "place_of_supply": f"{i.buyer_state}-{STATES.get(i.buyer_state, '')}",
                 "sac": sac, "taxable": r(i.taxable_paise), "cgst": r(i.cgst_paise), "sgst": r(i.sgst_paise), "igst": r(i.igst_paise),
                 "total": r(i.total_paise), "status": "void" if i.voided_at else "active"} for i in invs]
    b2b = [x for x in register if x["type"] == "B2B"]
    states: dict[str, dict] = {}
    for i in invs:
        if i.buyer_gstin:
            continue
        k = f"{i.buyer_state}-{STATES.get(i.buyer_state, '')}"
        s = states.setdefault(k, {"place_of_supply": k, "invoices": 0, "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0, "total": 0})
        s["invoices"] += 1
        for f, v in (("taxable", i.taxable_paise), ("cgst", i.cgst_paise), ("sgst", i.sgst_paise), ("igst", i.igst_paise), ("total", i.total_paise)):
            s[f] += v
    b2c = [{**s, **{f: r(s[f]) for f in ("taxable", "cgst", "sgst", "igst", "total")}} for s in sorted(states.values(), key=lambda x: x["place_of_supply"])]
    credit_notes = [{"credit_note_no": c.number, "date": f"{c.issued_at + IST:%d-%m-%Y}", "against_invoice": i.number,
                     "invoice_date": f"{i.issued_at + IST:%d-%m-%Y}", "buyer_gstin": i.buyer_gstin, "type": "B2B" if i.buyer_gstin else "B2C",
                     "place_of_supply": f"{i.buyer_state}-{STATES.get(i.buyer_state, '')}", "reason": c.reason, "taxable": r(c.taxable_paise),
                     "cgst": r(c.cgst_paise), "sgst": r(c.sgst_paise), "igst": r(c.igst_paise), "total": r(c.total_paise)} for c, i in cns]
    tot = lambda rows, f: round(sum(x[f] for x in rows), 2)  # noqa: E731
    gross = {f: tot(register, f) for f in ("taxable", "cgst", "sgst", "igst", "total")}
    credit = {f: tot(credit_notes, f) for f in ("taxable", "cgst", "sgst", "igst", "total")}
    hsn = [{"sac": sac, "description": "Online information and database access or retrieval services (AI text to speech)",
            "uqc": "NA", "quantity": len(register), "taxable": round(gross["taxable"] - credit["taxable"], 2),
            "igst": round(gross["igst"] - credit["igst"], 2), "cgst": round(gross["cgst"] - credit["cgst"], 2),
            "sgst": round(gross["sgst"] - credit["sgst"], 2)}]
    payments = [{"payment_id": x.rzp_payment_id, "date": f"{x.created_at + IST:%d-%m-%Y}", "amount": r(x.amount_paise), "status": x.status,
                 "method": x.method, "refunded": r(x.refunded_paise or 0), "net_received": r(x.amount_paise - (x.refunded_paise or 0))
                 if x.status in ("captured", "refunded") else 0, "invoice_no": num or ""} for x, num in pays]
    return {"month": month, "fy": financial_year(a + timedelta(days=1)), "sac": sac,
            "summary": {"invoices": len(register), "b2b": len(b2b), "b2c": len(register) - len(b2b), "credit_notes": len(credit_notes),
                        "gross": gross, "credit": credit, "net": {f: round(gross[f] - credit[f], 2) for f in gross},
                        "payments_received": round(sum(x["net_received"] for x in payments), 2)},
            "sheets": {"invoice_register": register, "b2b": b2b, "b2c_state_wise": b2c, "hsn_sac_summary": hsn,
                       "credit_notes": credit_notes, "payments_tds": payments}}


def _xlsx(rep: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["AiWazz GST report", rep["month"], f"FY {rep['fy']}", f"SAC {rep['sac']}"])
    ws.append([])
    for k in ("gross", "credit", "net"):
        ws.append([k.title(), *(f"{f}: {v}" for f, v in rep["summary"][k].items())])
    ws.append(["Invoices", rep["summary"]["invoices"], "B2B", rep["summary"]["b2b"], "B2C", rep["summary"]["b2c"]])
    ws.append(["Credit notes", rep["summary"]["credit_notes"], "Payments received (net)", rep["summary"]["payments_received"]])
    for name, rows in rep["sheets"].items():
        sh = wb.create_sheet(name[:31])
        if rows:
            sh.append(list(rows[0].keys()))
            for c in sh[1]:
                c.font = Font(bold=True)
            for row in rows:
                sh.append(list(row.values()))
        else:
            sh.append(["No rows this month"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/gst/report")
async def get_gst_report(request: Request, month: str = Query(pattern=r"^\d{4}-\d{2}$"),
                         format: str = Query("json", pattern="^(json|csv|xlsx)$"), sheet: str = Query("invoice_register", max_length=32),
                         p: Principal = Depends(require_perm("billing.read")), db: AsyncSession = Depends(get_db)):
    rep = await gst_report(db, month)
    if format == "json":
        return rep
    from .. import deps, rbac
    if not rbac.has(p.user.role, "billing.export"):
        raise HTTPException(403, "Your role doesn't allow this")
    if not deps.stepup_ok(p):
        raise HTTPException(403, "Confirm it's you (password + 2FA code) to continue", headers={"X-Step-Up": "required"})
    audit(db, request, p.user, "export.gst", target_type="gst_report", target_id=month, after={"format": format, "sheet": sheet}, full=True)
    await db.commit()
    if format == "csv":
        if sheet not in rep["sheets"]:
            raise HTTPException(422, f"Unknown sheet. Use one of: {', '.join(rep['sheets'])}")
        return csv_response(rep["sheets"][sheet], f"aiwazz-gst-{month}-{sheet}.csv")
    return Response(_xlsx(rep), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="aiwazz-gst-{month}.xlsx"'})

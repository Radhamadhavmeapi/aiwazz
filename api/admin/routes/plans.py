"""A3: plans & pricing (legal.json, validated write + diff preview + git commit + landing rebuild; price change →
new Razorpay plan versions, existing subscribers grandfathered), coupons, referral program settings."""
import copy
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from billing import routes as broutes
from billing.coupons import describe, normalize
from billing.razorpay import RazorpayError
from db import get_db, utcnow
from models import Coupon, CouponRedemption, PlanVersion, Subscription, User
from settings import get_settings

from .. import jobs, legal_store, settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
IST = timedelta(hours=5, minutes=30)
PAID = ("starter", "creator", "pro")


def _prices(d: dict) -> dict[tuple[str, str], int]:
    """{(plan, period): taxable paise} from a legal.json document (same rule as billing.gst.plan_prices)."""
    disc = d.get("yearlyDiscountPercent", 0)
    out = {}
    for p in d["plans"]:
        if p["id"] in PAID:
            out[(p["id"], "monthly")] = p["priceMonthly"] * 100
            out[(p["id"], "yearly")] = round(p["priceMonthly"] * (1 - disc / 100)) * 12 * 100
    return out


@router.get("/plans")
async def get_plans(p: Principal = Depends(require_perm("plans.read")), db: AsyncSession = Depends(get_db)):
    d = legal_store.read()
    versions = (await db.execute(select(PlanVersion).order_by(PlanVersion.id.desc()))).scalars().all()
    subs = dict((await db.execute(select(Subscription.rzp_plan_id, func.count()).where(Subscription.status.in_(
        ("active", "authenticated", "pending", "halted", "paused"))).group_by(Subscription.rzp_plan_id))).all())
    s = get_settings()
    return {
        "plans": d["plans"], "yearlyDiscountPercent": d["yearlyDiscountPercent"], "gstRatePercent": d["gstRatePercent"],
        "pricesIncludeGst": d.get("pricesIncludeGst", False),
        "versions": [{"id": v.id, "plan": v.plan, "period": v.period, "taxable_paise": v.taxable_paise, "total_paise": v.total_paise,
                      "rzp_plan_id": v.rzp_plan_id, "active": v.active, "created_at": iso(v.created_at),
                      "subscribers": subs.get(v.rzp_plan_id, 0) if v.rzp_plan_id else 0} for v in versions],
        "env_plan_ids": {k: {"id": v, "subscribers": subs.get(v, 0)} for k, v in s.razorpay_plan_ids.items()},
        "landing_job_running": jobs.is_running("landing-deploy"),
    }


class PlansIn(BaseModel):
    plans: list[dict] = Field(min_length=4, max_length=4)
    yearlyDiscountPercent: int = Field(ge=0, le=90)


def _proposed(body: PlansIn) -> tuple[dict, dict]:
    before = legal_store.read()
    after = copy.deepcopy(before)
    after["plans"] = [{k: v for k, v in p.items() if k in ("id", "name", "priceMonthly", "characters", "features", "visibility",
                                                             "sortOrder", "popular")} for p in body.plans]
    for p in after["plans"]:
        if not p.get("popular"):
            p.pop("popular", None)
        if p.get("visibility", "public") == "public":
            p.pop("visibility", None)
    after["yearlyDiscountPercent"] = body.yearlyDiscountPercent
    return before, after


@router.post("/plans/preview")
async def preview_plans(body: PlansIn, p: Principal = Depends(require_perm("plans.write")), db: AsyncSession = Depends(get_db)):
    before, after = _proposed(body)
    changes = legal_store.diff({"plans": before["plans"], "yearlyDiscountPercent": before["yearlyDiscountPercent"]},
                               {"plans": after["plans"], "yearlyDiscountPercent": after["yearlyDiscountPercent"]})
    old, new = _prices(before), _prices(after)
    price_changes = [{"plan": k[0], "period": k[1], "before_paise": old.get(k), "after_paise": v} for k, v in new.items() if old.get(k) != v]
    return {"errors": legal_store.validate(after), "changes": changes, "price_changes": price_changes,
            "note": "Existing subscribers keep their current price (grandfathered). New Razorpay plan versions are "
                    "created for changed prices" + ("" if get_settings().billing_enabled else " once Razorpay keys are set") + "."}


@router.put("/plans")
async def apply_plans(body: PlansIn, request: Request, p: Principal = Depends(require_perm("plans.write")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    from billing.gst import GST_RATE
    before, after = _proposed(body)
    if errs := legal_store.validate(after):
        raise HTTPException(422, "; ".join(errs))
    changes = legal_store.diff(before["plans"], after["plans"]) + legal_store.diff(
        before["yearlyDiscountPercent"], after["yearlyDiscountPercent"], "yearlyDiscountPercent")
    if not changes:
        raise HTTPException(422, "Nothing changed")
    old, new = _prices(before), _prices(after)
    created = []
    s = get_settings()
    for (plan, period), taxable in new.items():
        if old.get((plan, period)) == taxable:
            continue
        total = taxable * (100 + GST_RATE) // 100
        rzp_id = ""
        if s.billing_enabled:
            name = next(x["name"] for x in after["plans"] if x["id"] == plan)
            try:
                rp = await broutes.client().create_plan("monthly" if period == "monthly" else "yearly", total,
                                                         f"AiWazz {name} ({period})", f"₹{taxable // 100} + {GST_RATE}% GST",
                                                         {"plan": plan, "period": period, "version": utcnow().strftime("%Y%m%d%H%M")})
                rzp_id = rp["id"]
            except RazorpayError as e:
                raise HTTPException(502, f"Razorpay couldn't create the new plan version ({plan} {period}): {e}. Nothing was changed.") from e
        for v in (await db.execute(select(PlanVersion).where(PlanVersion.plan == plan, PlanVersion.period == period,
                                                             PlanVersion.active.is_(True)))).scalars():
            v.active = False
        db.add(PlanVersion(plan=plan, period=period, taxable_paise=taxable, total_paise=total, rzp_plan_id=rzp_id,
                           active=True, created_by=p.user.id))
        created.append({"plan": plan, "period": period, "total_paise": total, "rzp_plan_id": rzp_id})
    legal_store.write_atomic(after)
    try:
        sha = await legal_store.commit("Admin: update plans and pricing (legal.json)", p.user.email)
    except RuntimeError as e:
        legal_store.write_atomic(before)
        await db.rollback()
        raise HTTPException(500, f"Couldn't commit legal.json, nothing changed: {e}") from e
    legal_store.reload_in_process()
    audit(db, request, p.user, "plan.update", target_type="legal", target_id="plans", label=f"commit {sha}",
          after={"changes": changes, "new_versions": created}, full=True)
    await db.commit()
    started = jobs.start(request.app.state.sessionmaker, "landing-deploy", legal_store.push_and_rebuild_landing)
    return {"ok": True, "commit": sha, "new_versions": created, "landing_rebuild": "started" if started else "already running"}


# ── Coupons ──────────────────────────────────────────────────────────────────
def _coupon_row(c: Coupon, used: int = 0) -> dict:
    now = utcnow()
    state = "inactive" if not c.active else "scheduled" if c.starts_at and c.starts_at > now else \
        "expired" if c.ends_at and c.ends_at <= now else "used up" if c.max_redemptions is not None and used >= c.max_redemptions else "active"
    return {"id": c.id, "code": c.code, "description": c.description, "kind": c.kind, "value": c.value,
            "plans": [x for x in c.plans.split(",") if x], "periods": [x for x in c.periods.split(",") if x],
            "duration": c.duration, "cycles": c.cycles, "max_redemptions": c.max_redemptions, "per_user_limit": c.per_user_limit,
            "starts_at": iso(c.starts_at), "ends_at": iso(c.ends_at), "active": c.active, "rzp_offer_id": c.rzp_offer_id,
            "redemptions": used, "state": state, "summary": describe(c), "created_at": iso(c.created_at)}


async def _used(db, ids) -> dict[int, int]:
    if not ids:
        return {}
    return dict((await db.execute(select(CouponRedemption.coupon_id, func.count()).where(
        CouponRedemption.coupon_id.in_(ids), CouponRedemption.status != "void").group_by(CouponRedemption.coupon_id))).all())


@router.get("/coupons")
async def list_coupons(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("coupons.read")),
                       db: AsyncSession = Depends(get_db)):
    stmt = select(Coupon)
    if lp.q:
        stmt = stmt.where(Coupon.code.contains(lp.q.upper()) | Coupon.description.contains(lp.q))
    page = await respond(db, request, p, stmt, lp, sorts={"created_at": Coupon.created_at, "code": Coupon.code},
                         default_sort=Coupon.id.desc(), row=_coupon_row, name="coupons")
    if isinstance(page, dict):
        used = await _used(db, [c["id"] for c in page["items"]])
        for c in page["items"]:
            c["redemptions"] = used.get(c["id"], 0)
            if c["state"] == "active" and c["max_redemptions"] is not None and c["redemptions"] >= c["max_redemptions"]:
                c["state"] = "used up"
    return page


class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    description: str = Field("", max_length=255)
    kind: str = Field(pattern="^(percent|fixed)$")
    value: int = Field(ge=1)
    plans: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=lambda: ["monthly", "yearly"], min_length=1)
    duration: str = Field("once", pattern="^(once|cycles)$")
    cycles: int = Field(1, ge=1, le=36)
    max_redemptions: int | None = Field(default=None, ge=1)
    per_user_limit: int = Field(1, ge=1, le=10)
    starts_on: date | None = None
    ends_on: date | None = None       # last valid day (IST)
    active: bool = True
    rzp_offer_id: str = Field("", max_length=40, pattern=r"^(|offer_[A-Za-z0-9]+)$")


def _apply(c: Coupon, body: CouponIn) -> None:
    if body.kind == "percent" and body.value > 100:
        raise HTTPException(422, "A percentage can't be more than 100")
    if any(x not in PAID for x in body.plans) or any(x not in ("monthly", "yearly") for x in body.periods):
        raise HTTPException(422, "Unknown plan or period")
    if body.starts_on and body.ends_on and body.ends_on < body.starts_on:
        raise HTTPException(422, "The end date is before the start date")
    c.code, c.description, c.kind, c.value = normalize(body.code), body.description.strip(), body.kind, body.value
    c.plans, c.periods = ",".join(body.plans), ",".join(body.periods)
    c.duration, c.cycles = body.duration, body.cycles if body.duration == "cycles" else 1
    c.max_redemptions, c.per_user_limit, c.active, c.rzp_offer_id = body.max_redemptions, body.per_user_limit, body.active, body.rzp_offer_id
    c.starts_at = datetime.combine(body.starts_on, datetime.min.time()) - IST if body.starts_on else None
    c.ends_at = datetime.combine(body.ends_on, datetime.min.time()) + timedelta(days=1) - IST if body.ends_on else None


@router.post("/coupons")
async def create_coupon(body: CouponIn, request: Request, p: Principal = Depends(require_perm("coupons.write")),
                        db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Coupon.id).where(Coupon.code == normalize(body.code)))).first():
        raise HTTPException(409, "A coupon with this code already exists")
    c = Coupon(created_by=p.user.id)
    _apply(c, body)
    db.add(c)
    await db.flush()
    audit(db, request, p.user, "coupon.create", target_type="coupon", target_id=c.id, label=c.code, after=_coupon_row(c), full=True)
    await db.commit()
    return _coupon_row(c)


@router.put("/coupons/{cid}")
async def update_coupon(cid: int, body: CouponIn, request: Request, p: Principal = Depends(require_perm("coupons.write")),
                        db: AsyncSession = Depends(get_db)):
    c = await db.get(Coupon, cid)
    if c is None:
        raise HTTPException(404, "Coupon not found")
    before = _coupon_row(c)
    if normalize(body.code) != c.code:
        raise HTTPException(422, "The code can't be changed; create a new coupon")
    _apply(c, body)
    audit(db, request, p.user, "coupon.update", target_type="coupon", target_id=c.id, label=c.code, before=before, after=_coupon_row(c))
    await db.commit()
    return _coupon_row(c)


@router.get("/coupons/{cid}/redemptions")
async def coupon_redemptions(cid: int, request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("coupons.read")),
                             db: AsyncSession = Depends(get_db)):
    stmt = select(CouponRedemption, User.email).outerjoin(User, User.id == CouponRedemption.user_id).where(CouponRedemption.coupon_id == cid)
    return await respond(db, request, p, stmt, lp, scalars=False, name="redemptions", sorts={"created_at": CouponRedemption.created_at},
                         default_sort=CouponRedemption.id.desc(),
                         row=lambda r: {"id": r[0].id, "email": r[1] or "", "user_id": r[0].user_id, "status": r[0].status,
                                        "subscription_id": r[0].subscription_id, "created_at": iso(r[0].created_at)})


# ── Referral program (data model + settings; user-facing part behind the feature flag, off) ──
class ReferralIn(BaseModel):
    enabled: bool
    reward_chars_referrer: int = Field(ge=0, le=1_000_000)
    reward_chars_referred: int = Field(ge=0, le=1_000_000)
    require_paid: bool = True


@router.get("/settings/referrals")
async def get_referrals(p: Principal = Depends(require_perm("coupons.read")), db: AsyncSession = Depends(get_db)):
    from models import Referral
    counts = dict((await db.execute(select(Referral.status, func.count()).group_by(Referral.status))).all())
    return {**await settings_store.get(db, "referrals"), "counts": counts}


@router.put("/settings/referrals")
async def put_referrals(body: ReferralIn, request: Request, p: Principal = Depends(require_perm("coupons.write")),
                        db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "referrals")
    after = body.model_dump()
    await settings_store.put(db, "referrals", after, p.user.id)
    audit(db, request, p.user, "settings.referrals", target_type="setting", target_id="referrals", before=before, after=after)
    await db.commit()
    return after


@router.get("/jobs")
async def list_jobs(request: Request, lp: ListParams = Depends(), task: str = Query("", max_length=32),
                    p: Principal = Depends(require_perm("system.read")), db: AsyncSession = Depends(get_db)):
    from models import TaskRun
    stmt = select(TaskRun)
    if task:
        stmt = stmt.where(TaskRun.task == task)
    return await respond(db, request, p, stmt, lp, sorts={"started_at": TaskRun.started_at}, default_sort=TaskRun.id.desc(), name="jobs",
                         row=lambda t: {"id": t.id, "task": t.task, "started_at": iso(t.started_at), "finished_at": iso(t.finished_at),
                                        "status": t.status, "detail": t.detail})

"""A2: Invites (create with optional plan for early-access friends, copy once, revoke), waitlist ("Request an invite":
approve → invite + email, reject, bulk approve) and the signup mode (invite-only / open / closed)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from auth.security import new_invite_code, normalize_invite, sha256
from db import get_db, utcnow
from models import STAFF_ROLES, Invite, InviteRequest, User
from settings import get_settings
from usage import PLANS

from .. import rbac, settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, iso, respond
from .users import end_of_ist_day

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)


def invite_status(i: Invite) -> str:
    if i.revoked:
        return "revoked"
    if i.uses >= i.max_uses:
        return "used"
    if i.expires_at and i.expires_at <= utcnow():
        return "expired"
    return "active"


def _inv_out(i: Invite) -> dict:
    return {"id": i.id, "label": i.label, "email": i.email, "role": i.role, "uses": i.uses, "max_uses": i.max_uses,
            "expires_at": iso(i.expires_at), "plan": i.plan, "plan_until": iso(i.plan_until), "status": invite_status(i),
            "created_at": iso(i.created_at), "created_by": i.created_by}


@router.get("/invites")
async def list_invites(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                       p: Principal = Depends(require_perm("invites.read")), db: AsyncSession = Depends(get_db)):
    now = utcnow()
    stmt = select(Invite)
    if lp.q:
        stmt = stmt.where(Invite.label.contains(lp.q) | Invite.email.contains(lp.q.lower()))
    if status == "active":
        stmt = stmt.where(Invite.revoked.is_(False), Invite.uses < Invite.max_uses,
                          (Invite.expires_at.is_(None)) | (Invite.expires_at > now))
    elif status == "used":
        stmt = stmt.where(Invite.uses >= Invite.max_uses)
    elif status == "revoked":
        stmt = stmt.where(Invite.revoked.is_(True))
    elif status == "expired":
        stmt = stmt.where(Invite.revoked.is_(False), Invite.expires_at <= now, Invite.uses < Invite.max_uses)
    return await respond(db, request, p, stmt, lp, sorts={"created_at": Invite.created_at, "expires_at": Invite.expires_at},
                         default_sort=Invite.id.desc(), row=_inv_out, name="invites")


class InviteIn(BaseModel):
    uses: int = Field(1, ge=1, le=1000)
    days: int = Field(14, ge=1, le=365)
    role: str = Field("user", pattern="^(user|admin|support|finance|viewer)$")
    label: str = Field("", max_length=100)
    email: str = Field("", max_length=254)
    plan: str = Field("", pattern="^(|starter|creator|pro)$")
    plan_until: date | None = None


async def create_invite(db: AsyncSession, request: Request, p: Principal, body: InviteIn) -> tuple[Invite, str]:
    if body.role != "user" and not rbac.has(p.user.role, "roles.write"):
        raise HTTPException(403, "Only the owner can invite staff")
    if body.plan and body.plan_until and body.plan_until < (utcnow() + timedelta(hours=5, minutes=30)).date():
        raise HTTPException(422, "The plan end date is in the past")
    if body.plan_until and not body.plan:
        raise HTTPException(422, "Choose the plan the end date belongs to")
    code = new_invite_code()
    inv = Invite(code_hash=sha256(normalize_invite(code)), label=body.label.strip(), role=body.role, max_uses=body.uses,
                 expires_at=utcnow() + timedelta(days=body.days), created_by=p.user.id, email=body.email.strip().lower(),
                 plan=body.plan or None, plan_until=end_of_ist_day(body.plan_until) if body.plan_until else None)
    db.add(inv)
    await db.flush()
    audit(db, request, p.user, "invite.create", target_type="invite", target_id=inv.id, label=inv.label or inv.email,
          after=_inv_out(inv), full=True)
    return inv, code


@router.post("/invites")
async def new_invite(body: InviteIn, request: Request, p: Principal = Depends(require_perm("invites.write")),
                     db: AsyncSession = Depends(get_db)):
    inv, code = await create_invite(db, request, p, body)
    await db.commit()
    return _inv_out(inv) | {"code": code, "signup_url": f"https://login.aiwazz.in/signup?invite={code}"}   # shown once


@router.post("/invites/{iid}/revoke")
async def revoke_invite(iid: int, request: Request, p: Principal = Depends(require_perm("invites.write")),
                        db: AsyncSession = Depends(get_db)):
    inv = await db.get(Invite, iid)
    if inv is None:
        raise HTTPException(404, "Invite not found")
    if inv.role in STAFF_ROLES and not rbac.has(p.user.role, "roles.write"):
        raise HTTPException(403, "Only the owner can revoke staff invites")
    inv.revoked = True
    audit(db, request, p.user, "invite.revoke", target_type="invite", target_id=iid, label=inv.label or inv.email)
    await db.commit()
    return _inv_out(inv)


# ── Waitlist ─────────────────────────────────────────────────────────────────
def _req_out(r: InviteRequest, registered: bool = False) -> dict:
    return {"id": r.id, "email": r.email, "name": r.name, "use_case": r.use_case, "status": r.status,
            "created_at": iso(r.created_at), "updated_at": iso(r.updated_at), "reviewed_at": iso(r.reviewed_at),
            "invite_id": r.invite_id, "registered": registered}


@router.get("/invite-requests")
async def list_requests(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                        p: Principal = Depends(require_perm("invites.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(InviteRequest)
    if status:
        stmt = stmt.where(InviteRequest.status == status)
    if lp.q:
        stmt = stmt.where(InviteRequest.email.contains(lp.q.lower()) | InviteRequest.name.contains(lp.q) |
                          InviteRequest.use_case.contains(lp.q))
    page = await respond(db, request, p, stmt, lp, sorts={"created_at": InviteRequest.created_at, "email": InviteRequest.email},
                         default_sort=InviteRequest.id.desc(), row=_req_out, name="waitlist")
    if isinstance(page, dict) and page["items"]:
        emails = [i["email"] for i in page["items"]]
        reg = set((await db.execute(select(User.email).where(User.email.in_(emails)))).scalars())
        for i in page["items"]:
            i["registered"] = i["email"] in reg
    return page


class ApproveIn(BaseModel):
    plan: str = Field("", pattern="^(|starter|creator|pro)$")
    plan_until: date | None = None
    days: int = Field(14, ge=1, le=90)
    send_email: bool = True


async def _approve(db, request, p, r: InviteRequest, body: ApproveIn) -> dict:
    from emails import send_template
    if r.status == "invited" and r.invite_id:
        raise HTTPException(409, f"{r.email} was already invited")
    inv, code = await create_invite(db, request, p, InviteIn(uses=1, days=body.days, label=f"waitlist: {r.email}"[:100],
                                                            email=r.email, plan=body.plan, plan_until=body.plan_until))
    r.status, r.reviewed_by, r.reviewed_at, r.invite_id = "invited", p.user.id, utcnow(), inv.id
    email_status = "not_sent"
    if body.send_email:
        plan_note = ""
        if body.plan:
            plan_note = f"Your account starts on the {PLANS[body.plan]['name']} plan" + \
                (f" until {body.plan_until:%d %b %Y}" if body.plan_until else "") + ", free.\n\n"
        email_status = await send_template(db, "invite", r.email, {
            "name": r.name or r.email.split("@")[0], "code": code, "signup_url": f"https://login.aiwazz.in/signup?invite={code}",
            "plan_note": plan_note, "expires": f"{inv.expires_at:%d %b %Y}"})
    audit(db, request, p.user, "invite.request.approve", target_type="invite_request", target_id=r.id, label=r.email,
          after={"invite_id": inv.id, "plan": body.plan, "email": email_status}, full=True)
    # The code is returned so staff can share it by hand while mail is off (shown once, never stored).
    return {"id": r.id, "email": r.email, "invite_id": inv.id, "code": code, "email_status": email_status,
            "signup_url": f"https://login.aiwazz.in/signup?invite={code}"}


async def _get_req(db, rid) -> InviteRequest:
    r = await db.get(InviteRequest, rid)
    if r is None:
        raise HTTPException(404, "Request not found")
    return r


@router.post("/invite-requests/{rid}/approve")
async def approve(rid: int, body: ApproveIn, request: Request, p: Principal = Depends(require_perm("invites.write")),
                  db: AsyncSession = Depends(get_db)):
    out = await _approve(db, request, p, await _get_req(db, rid), body)
    await db.commit()
    return out


class RejectIn(BaseModel):
    send_email: bool = False


@router.post("/invite-requests/{rid}/reject")
async def reject(rid: int, body: RejectIn, request: Request, p: Principal = Depends(require_perm("invites.write")),
                 db: AsyncSession = Depends(get_db)):
    from emails import send_template
    r = await _get_req(db, rid)
    r.status, r.reviewed_by, r.reviewed_at = "declined", p.user.id, utcnow()
    email_status = await send_template(db, "invite_declined", r.email, {"name": r.name or r.email.split("@")[0]}) \
        if body.send_email else "not_sent"
    audit(db, request, p.user, "invite.request.reject", target_type="invite_request", target_id=r.id, label=r.email,
          after={"email": email_status}, full=True)
    await db.commit()
    return _req_out(r)


class BulkApproveIn(ApproveIn):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/invite-requests/bulk-approve")
async def bulk_approve(body: BulkApproveIn, request: Request, p: Principal = Depends(require_perm("invites.write")),
                       db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(InviteRequest).where(InviteRequest.id.in_(body.ids)))).scalars().all()
    out, skipped = [], []
    for r in rows:
        if r.status == "invited" and r.invite_id:
            skipped.append(r.email)
            continue
        out.append(await _approve(db, request, p, r, body))
    await db.commit()
    return {"approved": out, "skipped": skipped}


# ── Signup mode ──────────────────────────────────────────────────────────────
class SignupModeIn(BaseModel):
    signup_mode: str = Field(pattern="^(invite|open|closed)$")


@router.get("/settings/signup")
async def get_signup_mode(p: Principal = Depends(require_perm("invites.read")), db: AsyncSession = Depends(get_db)):
    return {"signup_mode": (await settings_store.get(db, "general"))["signup_mode"]}


@router.put("/settings/signup")
async def put_signup_mode(body: SignupModeIn, request: Request, p: Principal = Depends(require_perm("settings.write")),
                          _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "general")
    after = {**before, "signup_mode": body.signup_mode}
    await settings_store.put(db, "general", after, p.user.id)
    audit(db, request, p.user, "settings.signup_mode", target_type="setting", target_id="general",
          before={"signup_mode": before["signup_mode"]}, after={"signup_mode": body.signup_mode})
    await db.commit()
    return {"signup_mode": body.signup_mode}

"""A7: compliance (DPDP requests with due dates, consent records, deletion log, policy history, legal.json editor),
settings (general, limits, feature flags, payments TEST/LIVE checklist, integrations) and team & roles."""
import copy
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from db import get_db, utcnow
from models import (STAFF_ROLES, DeletionLog, DsrRequest, Invite, Payment, TotpSecret, User, UserSession, WebhookEvent)
from settings import get_settings

from .. import jobs, legal_store, rbac, settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
DSR_DAYS = {"access": 30, "correction": 30, "deletion": 30, "grievance": 15}


# ── DPDP requests ────────────────────────────────────────────────────────────
def _dsr(d: DsrRequest) -> dict:
    return {"id": d.id, "kind": d.kind, "email": d.email, "user_id": d.user_id, "status": d.status, "details": d.details, "notes": d.notes,
            "ticket_id": d.ticket_id, "received_at": iso(d.received_at), "due_at": iso(d.due_at), "completed_at": iso(d.completed_at),
            "overdue": d.status in ("new", "in_progress") and d.due_at < utcnow()}


@router.get("/dsr")
async def list_dsr(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16), kind: str = Query("", max_length=16),
                   p: Principal = Depends(require_perm("compliance.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(DsrRequest)
    if status == "open":
        stmt = stmt.where(DsrRequest.status.in_(("new", "in_progress")))
    elif status:
        stmt = stmt.where(DsrRequest.status == status)
    if kind:
        stmt = stmt.where(DsrRequest.kind == kind)
    if lp.q:
        stmt = stmt.where(DsrRequest.email.contains(lp.q.lower()))
    return await respond(db, request, p, stmt, lp, sorts={"received_at": DsrRequest.received_at, "due_at": DsrRequest.due_at},
                         default_sort=DsrRequest.due_at.asc(), row=_dsr, name="dsr")


class DsrIn(BaseModel):
    kind: str = Field(pattern="^(access|correction|deletion|grievance)$")
    email: str = Field(min_length=3, max_length=254)
    details: str = Field("", max_length=2000)
    ticket_id: int | None = None


@router.post("/dsr")
async def create_dsr(body: DsrIn, request: Request, p: Principal = Depends(require_perm("compliance.write")), db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    now = utcnow()
    d = DsrRequest(kind=body.kind, email=email, user_id=user.id if user else None, details=body.details, ticket_id=body.ticket_id,
                   received_at=now, due_at=now + timedelta(days=DSR_DAYS[body.kind]))
    db.add(d)
    await db.flush()
    audit(db, request, p.user, "compliance.dsr.create", target_type="dsr", target_id=d.id, label=email, after=_dsr(d), full=True)
    await db.commit()
    return _dsr(d)


class DsrUpdateIn(BaseModel):
    status: str = Field(pattern="^(new|in_progress|done|rejected)$")
    notes: str = Field("", max_length=2000)


@router.patch("/dsr/{did}")
async def update_dsr(did: int, body: DsrUpdateIn, request: Request, p: Principal = Depends(require_perm("compliance.write")),
                     db: AsyncSession = Depends(get_db)):
    d = await db.get(DsrRequest, did)
    if d is None:
        raise HTTPException(404, "Not found")
    before = _dsr(d)
    d.status, d.notes, d.handled_by = body.status, body.notes, p.user.id
    d.completed_at = utcnow() if body.status in ("done", "rejected") else None
    audit(db, request, p.user, "compliance.dsr.update", target_type="dsr", target_id=d.id, label=d.email, before=before, after=_dsr(d))
    await db.commit()
    return _dsr(d)


@router.get("/compliance/consents")
async def consents(request: Request, lp: ListParams = Depends(), marketing: str = Query("", pattern="^(|yes|no)$"),
                   p: Principal = Depends(require_perm("compliance.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(User)
    if lp.q:
        stmt = stmt.where(or_(User.email.contains(lp.q.lower()), User.terms_version.contains(lp.q)))
    if marketing:
        stmt = stmt.where(User.marketing_opt_in.is_(marketing == "yes"))
    return await respond(db, request, p, stmt, lp, sorts={"consent_at": User.consent_at}, default_sort=User.id.desc(), name="consents",
                         row=lambda u: {"id": u.id, "email": u.email, "consent_at": iso(u.consent_at), "terms_version": u.terms_version,
                                        "consent_ip": u.consent_ip, "marketing_opt_in": u.marketing_opt_in})


@router.get("/compliance/deletions")
async def deletions(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("compliance.read")),
                    db: AsyncSession = Depends(get_db)):
    """Deletion references (no email in clear text: search by email compares its SHA-256)."""
    from auth.security import sha256
    stmt = select(DeletionLog)
    if lp.q:
        stmt = stmt.where(or_(DeletionLog.reference.contains(lp.q.upper()), DeletionLog.email_hash == sha256(lp.q.strip().lower())))
    return await respond(db, request, p, stmt, lp, sorts={"created_at": DeletionLog.created_at}, default_sort=DeletionLog.id.desc(),
                         name="deletions", row=lambda d: {"id": d.id, "reference": d.reference, "generations_deleted": d.generations_deleted,
                                                          "created_at": iso(d.created_at)})


@router.get("/compliance/policy-history")
async def policy_history(p: Principal = Depends(require_perm("compliance.read"))):
    """When the legal pages / legal.json changed (git history of legal/)."""
    rows = []
    for line in (await _git_log()).splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            rows.append({"commit": parts[0], "date": parts[1], "author": parts[2], "message": parts[3]})
    d = legal_store.read()
    return {"items": rows, "current": {"effectiveDate": d.get("effectiveDate"), "lastUpdated": d.get("lastUpdated")}}


async def _git_log() -> str:
    import asyncio
    proc = await asyncio.create_subprocess_exec("git", "log", "--date=short", "--format=%h|%ad|%an|%s", "-n", "100", "--", "legal/",
                                                cwd=str(jobs.ROOT), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    return out.decode("utf-8", "replace")


# ── legal.json editor (company data; plans are edited in Plans & pricing) ───
@router.get("/legal")
async def get_legal(p: Principal = Depends(require_perm("compliance.read"))):
    d = legal_store.read()
    return {"data": {k: v for k, v in d.items() if k != "plans"}, "landing_job_running": jobs.is_running("landing-deploy")}


class LegalIn(BaseModel):
    data: dict


def _proposed_legal(body: LegalIn) -> tuple[dict, dict]:
    before = legal_store.read()
    after = copy.deepcopy(body.data)
    after["plans"] = before["plans"]                 # plans are not edited here
    return before, after


@router.post("/legal/preview")
async def preview_legal(body: LegalIn, p: Principal = Depends(require_perm("legal.write"))):
    before, after = _proposed_legal(body)
    return {"errors": legal_store.validate(after), "changes": legal_store.diff(before, after)}


@router.put("/legal")
async def save_legal(body: LegalIn, request: Request, p: Principal = Depends(require_perm("legal.write")),
                     _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    before, after = _proposed_legal(body)
    if errs := legal_store.validate(after):
        raise HTTPException(422, "; ".join(errs))
    changes = legal_store.diff(before, after)
    if not changes:
        raise HTTPException(422, "Nothing changed")
    legal_store.write_atomic(after)
    try:
        sha = await legal_store.commit("Admin: update company / legal data (legal.json)", p.user.email)
    except RuntimeError as e:
        legal_store.write_atomic(before)
        raise HTTPException(500, f"Couldn't commit legal.json, nothing changed: {e}") from e
    legal_store.reload_in_process()
    audit(db, request, p.user, "legal.update", target_type="legal", target_id="legal.json", label=f"commit {sha}",
          after={"changes": changes}, full=True)
    await db.commit()
    started = jobs.start(request.app.state.sessionmaker, "landing-deploy", legal_store.push_and_rebuild_landing)
    return {"ok": True, "commit": sha, "landing_rebuild": "started" if started else "already running"}


# ── Settings: general, limits, flags, payments, integrations ─────────────────
def apply_limits(v: dict) -> None:
    """Runtime limits from admin → Settings override api/.env for this process (also applied at startup)."""
    from tts import jobs as tts_jobs
    s = get_settings()
    s.max_chars = int(v.get("max_chars", s.max_chars))
    s.audio_retention_days = int(v.get("retention_days", s.audio_retention_days))
    tts_jobs.MAX_PENDING_PER_USER = int(v.get("queue_per_user", tts_jobs.MAX_PENDING_PER_USER))


@router.get("/settings/all")
async def all_settings(p: Principal = Depends(require_perm("settings.read")), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    from tts import jobs as tts_jobs
    general = await settings_store.get(db, "general")
    limits = await settings_store.get(db, "limits")
    limits = {**limits, "max_chars": s.max_chars, "retention_days": s.audio_retention_days, "queue_per_user": tts_jobs.MAX_PENDING_PER_USER}
    referrals = await settings_store.get(db, "referrals")
    flags = {**await settings_store.get(db, "flags"), "referrals": referrals["enabled"], "open_signup": general["signup_mode"] == "open"}
    return {"general": general, "limits": limits, "flags": flags, "payments": await payments_state(db), "integrations": await integrations(db)}


class GeneralIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=40)
    support_email: str = Field(min_length=3, max_length=254)
    signup_mode: str = Field(pattern="^(invite|open|closed)$")


@router.put("/settings/general")
async def put_general(body: GeneralIn, request: Request, p: Principal = Depends(require_perm("settings.write")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    if "@" not in body.support_email:
        raise HTTPException(422, "Not an email address")
    before = await settings_store.get(db, "general")
    after = {**before, **body.model_dump()}
    await settings_store.put(db, "general", after, p.user.id)
    audit(db, request, p.user, "settings.general", target_type="setting", target_id="general", before=before, after=after)
    await db.commit()
    return after


class LimitsAllIn(BaseModel):
    max_chars: int = Field(ge=100, le=20000)
    queue_per_user: int = Field(ge=1, le=20)
    retention_days: int = Field(ge=1, le=90)


@router.put("/settings/limits")
async def put_limits(body: LimitsAllIn, request: Request, p: Principal = Depends(require_perm("settings.write")),
                     db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "limits")
    after = {**before, **body.model_dump()}
    await settings_store.put(db, "limits", after, p.user.id)
    apply_limits(after)
    audit(db, request, p.user, "settings.limits", target_type="setting", target_id="limits", before=before, after=after)
    await db.commit()
    return after


class FlagsIn(BaseModel):
    premium_voices: bool = False
    hinglish_default: bool = False
    referrals: bool = False
    open_signup: bool = False


@router.put("/settings/flags")
async def put_flags(body: FlagsIn, request: Request, p: Principal = Depends(require_perm("settings.write")),
                    _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "flags")
    await settings_store.put(db, "flags", {"premium_voices": body.premium_voices, "hinglish_default": body.hinglish_default}, p.user.id)
    ref = await settings_store.get(db, "referrals")
    await settings_store.put(db, "referrals", {**ref, "enabled": body.referrals}, p.user.id)
    general = await settings_store.get(db, "general")
    if body.open_signup != (general["signup_mode"] == "open"):
        await settings_store.put(db, "general", {**general, "signup_mode": "open" if body.open_signup else "invite"}, p.user.id)
    audit(db, request, p.user, "settings.flags", target_type="setting", target_id="flags",
          before={**before, "referrals": ref["enabled"], "open_signup": general["signup_mode"] == "open"}, after=body.model_dump())
    await db.commit()
    return body.model_dump()


async def payments_state(db: AsyncSession) -> dict:
    s = get_settings()
    mode = "OFF" if not s.razorpay_key_id else "TEST" if s.billing_test_mode else "LIVE"
    from models import PlanVersion
    plans_ok = bool(s.razorpay_plan_ids) or bool((await db.execute(select(PlanVersion.id).where(PlanVersion.rzp_plan_id != "")
                                                                  .limit(1))).first())
    webhook_ok = bool((await db.execute(select(WebhookEvent.id).where(WebhookEvent.signature_ok.is_(True),
                                                                      WebhookEvent.status == "processed").limit(1))).first())
    test_payment = bool((await db.execute(select(Payment.id).where(Payment.status.in_(("captured", "refunded"))).limit(1))).first())
    approval = await settings_store.get(db, "payments")
    checklist = [{"key": "keys", "label": "Razorpay key id + secret set", "ok": bool(s.razorpay_key_id and s.razorpay_key_secret)},
                 {"key": "webhook_secret", "label": "Webhook secret set", "ok": bool(s.razorpay_webhook_secret)},
                 {"key": "plans", "label": "Razorpay plans created", "ok": plans_ok},
                 {"key": "webhook", "label": "A signed webhook was received and processed", "ok": webhook_ok},
                 {"key": "test_payment", "label": "A test payment went through end to end", "ok": test_payment}]
    return {"mode": mode, "checklist": checklist, "ready_for_live": all(c["ok"] for c in checklist),
            "live_approved": approval.get("live_approved", False), "approved_by": approval.get("approved_by"),
            "approved_at": approval.get("approved_at")}


class GoLiveIn(BaseModel):
    approve: bool
    confirm: str = Field(max_length=16)


@router.post("/settings/payments/live")
async def approve_live(body: GoLiveIn, request: Request, p: Principal = Depends(require_perm("payments.mode")),
                       _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    """Owner approval to take LIVE payments. Keys themselves are set on the server (manage.py set-secret): secrets
    never pass through the panel. With LIVE keys and no approval, checkout stays closed."""
    st = await payments_state(db)
    if body.approve:
        if body.confirm != "GO LIVE":
            raise HTTPException(422, 'Type GO LIVE to confirm')
        if st["mode"] == "TEST" and not st["ready_for_live"]:
            raise HTTPException(409, "Finish the checklist in TEST mode first")
    after = {"live_approved": body.approve, "approved_by": p.user.email if body.approve else None,
             "approved_at": iso(utcnow()) if body.approve else None}
    await settings_store.put(db, "payments", after, p.user.id)
    audit(db, request, p.user, "settings.payments.live", target_type="setting", target_id="payments",
          before={"live_approved": st["live_approved"]}, after=after)
    await db.commit()
    return await payments_state(db)


async def integrations(db: AsyncSession) -> list[dict]:
    s = get_settings()
    return [
        {"name": "Razorpay", "status": "LIVE" if s.razorpay_key_id.startswith("rzp_live_") else "TEST" if s.razorpay_key_id else "not set",
         "detail": f"key id {'set' if s.razorpay_key_id else 'not set'} · secret {'set' if s.razorpay_key_secret else 'not set'} · "
                   f"webhook secret {'set' if s.razorpay_webhook_secret else 'not set'}"},
        {"name": "Mail (Postfix on this server)", "status": "on" if s.mail_enabled else "off",
         "detail": f"SMTP {s.smtp_host}:{s.smtp_port} · user {'set' if s.smtp_user else 'not set'} · password {'set' if s.smtp_password else 'not set'}"},
        {"name": "Studio voice worker", "status": "configured" if s.clone_secret else "off", "detail": f"{s.clone_url} · secret {'set' if s.clone_secret else 'not set'}"},
        {"name": "Backups", "status": "configured" if s.backup_passphrase else "off", "detail": "daily, encrypted, 14 days"},
        {"name": "2FA encryption key", "status": "set" if s.admin_secret_key else "not set", "detail": "AIWAZZ_ADMIN_SECRET_KEY"},
    ]


# ── Team & roles ─────────────────────────────────────────────────────────────
@router.get("/team")
async def team(p: Principal = Depends(require_perm("team.read")), db: AsyncSession = Depends(get_db)):
    from models import AdminAudit
    staff = (await db.execute(select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.id))).scalars().all()
    mfa = {t.user_id: t for t in (await db.execute(select(TotpSecret))).scalars()}
    last_action = dict((await db.execute(select(AdminAudit.actor_id, func.max(AdminAudit.at)).group_by(AdminAudit.actor_id))).all())
    invites = (await db.execute(select(Invite).where(Invite.role.in_(STAFF_ROLES), Invite.revoked.is_(False), Invite.uses < Invite.max_uses,
                                                     or_(Invite.expires_at.is_(None), Invite.expires_at > utcnow())))).scalars().all()
    return {"staff": [{"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.is_active and not u.suspended_at,
                       "mfa": bool(mfa.get(u.id) and mfa[u.id].enabled_at), "last_login_at": iso(u.last_login_at),
                       "last_action_at": iso(last_action.get(u.id)), "you": u.id == p.user.id} for u in staff],
            "invites": [{"id": i.id, "email": i.email, "role": i.role, "expires_at": iso(i.expires_at), "label": i.label} for i in invites],
            "roles": {r: sorted(rbac.ROLE_PERMS[r]) for r in STAFF_ROLES}}


class StaffInviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern="^(admin|support|finance|viewer)$")


@router.post("/team/invite")
async def invite_staff(body: StaffInviteIn, request: Request, p: Principal = Depends(require_perm("roles.write")),
                       db: AsyncSession = Depends(get_db)):
    from emails import send_template

    from .invites import InviteIn, create_invite
    email = body.email.strip().lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"{email} already has an account: change its role below instead")
    inv, code = await create_invite(db, request, p, InviteIn(uses=1, days=7, role=body.role, label=f"staff: {email}", email=email))
    status = await send_template(db, "invite", email, {"name": email.split("@")[0], "code": code, "signup_url": f"https://login.aiwazz.in/signup?invite={code}",
                                 "plan_note": f"You're joining the AiWazz team as {body.role}. After signing up, open https://login.aiwazz.in/admin "
                                              "and set up two-factor authentication.\n\n", "expires": f"{inv.expires_at:%d %b %Y}"})
    audit(db, request, p.user, "team.invite", target_type="invite", target_id=inv.id, label=email, after={"role": body.role, "email": status}, full=True)
    await db.commit()
    return {"code": code, "signup_url": f"https://login.aiwazz.in/signup?invite={code}", "email_status": status}


async def _staff_target(db, uid: int, p: Principal) -> User:
    u = await db.get(User, uid)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == p.user.id:
        raise HTTPException(422, "You can't change your own role or access here")
    if u.role == "owner":
        raise HTTPException(422, "Transfer ownership instead")
    return u


class RoleIn(BaseModel):
    role: str = Field(pattern="^(admin|support|finance|viewer|user)$")


async def _lock_sessions(db, uid: int) -> None:
    await db.execute(update(UserSession).where(UserSession.user_id == uid).values(mfa_at=None, admin_seen_at=None, stepup_until=None))


@router.put("/team/{uid}/role")
async def change_role(uid: int, body: RoleIn, request: Request, p: Principal = Depends(require_perm("roles.write")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    u = await _staff_target(db, uid, p)
    before = u.role
    u.role = body.role
    await _lock_sessions(db, u.id)
    audit(db, request, p.user, "team.role.change", target_type="user", target_id=u.id, label=u.email, before={"role": before}, after={"role": body.role})
    await db.commit()
    return {"ok": True, "role": u.role}


class ActiveIn(BaseModel):
    active: bool
    reason: str = Field(min_length=3, max_length=255)


@router.post("/team/{uid}/active")
async def set_active(uid: int, body: ActiveIn, request: Request, p: Principal = Depends(require_perm("roles.write")),
                     _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    u = await _staff_target(db, uid, p)
    u.is_active = body.active
    if not body.active:
        await db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    audit(db, request, p.user, "team.activate" if body.active else "team.deactivate", target_type="user", target_id=u.id, label=u.email, reason=body.reason)
    await db.commit()
    return {"ok": True}


@router.post("/team/{uid}/reset-2fa")
async def reset_2fa(uid: int, request: Request, p: Principal = Depends(require_perm("roles.write")),
                    _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    from models import BackupCode
    u = await _staff_target(db, uid, p)
    await db.execute(delete(BackupCode).where(BackupCode.user_id == u.id))
    await db.execute(delete(TotpSecret).where(TotpSecret.user_id == u.id))
    await _lock_sessions(db, u.id)
    audit(db, request, p.user, "mfa.reset", target_type="user", target_id=u.id, label=u.email)
    await db.commit()
    return {"ok": True}


class TransferIn(BaseModel):
    user_id: int
    confirm_email: str = Field(max_length=254)


@router.post("/team/transfer-ownership")
async def transfer_ownership(body: TransferIn, request: Request, p: Principal = Depends(require_perm("ownership.transfer")),
                             _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    u = await _staff_target(db, body.user_id, p)
    if u.role != "admin":
        raise HTTPException(422, "Make them an admin first; ownership goes to an admin")
    t = await db.get(TotpSecret, u.id)
    if t is None or t.enabled_at is None:
        raise HTTPException(422, "They need 2FA set up before they can become the owner")
    if body.confirm_email.strip().lower() != u.email:
        raise HTTPException(422, "Type their email to confirm")
    me = await db.get(User, p.user.id)
    me.role, u.role = "admin", "owner"
    await _lock_sessions(db, u.id)
    audit(db, request, p.user, "team.ownership.transfer", target_type="user", target_id=u.id, label=u.email,
          before={"owner": me.email}, after={"owner": u.email})
    await db.commit()
    return {"ok": True}

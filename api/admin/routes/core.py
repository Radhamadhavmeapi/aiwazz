"""A1: admin session state, 2FA (TOTP) setup / verify, backup codes, step-up re-auth, lock, sign out admin sessions,
audit log, security settings (IP allowlist)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import ratelimit
from auth.deps import Principal, client_ip, csrf_protect
from auth.security import verify_password
from db import get_db, utcnow
from models import AdminAudit, BackupCode, TotpSecret, User, UserSession
from settings import get_settings

from .. import rbac, settings_store, totp
from ..audit import audit
from ..deps import ip_allowed, require_perm, require_stepup, require_unlocked, staff_principal, stepup_ok, unlocked_state
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
WINDOW = 15 * 60


def _redis(request: Request):
    return request.app.state.redis


async def _limit(request: Request, key: str, n: int, window: int = WINDOW) -> None:
    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, key, n, window)
    if not lim.allowed:
        mins = max(1, round(lim.retry_after / 60))
        raise HTTPException(429, f"Too many attempts. Try again in {mins} minute{'s' if mins > 1 else ''}.",
                            headers={"Retry-After": str(lim.retry_after)})


def _payments_env() -> str:
    s = get_settings()
    if not s.razorpay_key_id:
        return "OFF"
    return "TEST" if s.billing_test_mode else "LIVE"


# ── Session state ────────────────────────────────────────────────────────────
@router.get("/me")
async def me(p: Principal = Depends(staff_principal), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    t = await db.get(TotpSecret, p.user.id)
    enrolled = bool(t and t.enabled_at)
    unlocked = enrolled and unlocked_state(p)
    left = (await db.execute(select(BackupCode.id).where(BackupCode.user_id == p.user.id, BackupCode.used_at.is_(None)))).all()
    return {
        "user": {"id": p.user.id, "email": p.user.email, "role": p.user.role, "name": p.user.name},
        "perms": sorted(rbac.perms_for(p.user.role)) if unlocked else [],
        "mfa": {"enrolled": enrolled, "unlocked": unlocked, "backup_codes_left": len(left) if enrolled else 0,
                "configured": bool(s.admin_secret_key)},
        "stepup_until": iso(p.session.stepup_until) if stepup_ok(p) else None,
        "idle_minutes": s.admin_idle_minutes, "stepup_minutes": s.stepup_minutes,
        "payments_env": _payments_env(),
    }


# ── 2FA enrolment ────────────────────────────────────────────────────────────
class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@router.post("/mfa/setup")
async def mfa_setup(body: PasswordIn, request: Request, p: Principal = Depends(staff_principal),
                    db: AsyncSession = Depends(get_db)):
    """Start (or restart) enrolment: needs the account password, returns the secret + QR once. Not yet active."""
    await _limit(request, f"admin:mfa-setup:{p.user.id}", 5)
    t = await db.get(TotpSecret, p.user.id)
    if t and t.enabled_at:
        raise HTTPException(409, "2FA is already set up. Use a backup code if you lost your phone, or ask the owner.")
    if not verify_password(p.user.password_hash, body.password):
        audit(db, request, p.user, "mfa.setup.bad_password", target_type="user", target_id=p.user.id)
        await db.commit()
        raise HTTPException(422, "Your password is incorrect")
    try:
        secret = totp.new_secret()
        enc = totp.encrypt(secret)
    except totp.NotConfigured as e:
        raise HTTPException(503, "2FA isn't configured on the server yet (AIWAZZ_ADMIN_SECRET_KEY)") from e
    if t is None:
        db.add(TotpSecret(user_id=p.user.id, secret_enc=enc))
    else:
        t.secret_enc, t.last_step, t.created_at = enc, 0, utcnow()
    audit(db, request, p.user, "mfa.setup.start", target_type="user", target_id=p.user.id, label=p.user.email)
    await db.commit()
    uri = totp.provisioning_uri(secret, p.user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": totp.qr_svg(uri)}


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


async def _new_backup_codes(db: AsyncSession, user_id: int) -> list[str]:
    await db.execute(delete(BackupCode).where(BackupCode.user_id == user_id))
    codes = totp.new_backup_codes()
    for c in codes:
        db.add(BackupCode(user_id=user_id, code_hash=totp.backup_hash(c)))
    return codes


def _unlock(sess: UserSession) -> None:
    now = utcnow()
    sess.mfa_at = sess.admin_seen_at = now


@router.post("/mfa/enable")
async def mfa_enable(body: CodeIn, request: Request, p: Principal = Depends(staff_principal),
                     db: AsyncSession = Depends(get_db)):
    await _limit(request, f"admin:mfa-enable:{p.user.id}", 10)
    t = await db.get(TotpSecret, p.user.id)
    if t is None or t.enabled_at:
        raise HTTPException(409, "Start the 2FA setup first")
    if utcnow() - t.created_at > timedelta(minutes=30):
        raise HTTPException(422, "This setup expired. Start again.")
    step = totp.verify(totp.decrypt(t.secret_enc), body.code, t.last_step)
    if step is None:
        raise HTTPException(422, "That code didn't match. Check the time on your phone and try the newest code.")
    t.enabled_at, t.last_step = utcnow(), step
    codes = await _new_backup_codes(db, p.user.id)
    _unlock(p.session)
    audit(db, request, p.user, "mfa.enable", target_type="user", target_id=p.user.id, label=p.user.email)
    await db.commit()
    return {"backup_codes": codes}


async def check_second_factor(db: AsyncSession, user: User, code: str) -> str | None:
    """'totp' / 'backup' if the code is valid (consumes it), else None."""
    t = await db.get(TotpSecret, user.id)
    if t is None or t.enabled_at is None:
        return None
    if totp.looks_like_backup(code):
        bc = (await db.execute(select(BackupCode).where(BackupCode.user_id == user.id, BackupCode.used_at.is_(None),
                                                         BackupCode.code_hash == totp.backup_hash(code)))).scalar_one_or_none()
        if bc is None:
            return None
        bc.used_at = utcnow()
        return "backup"
    step = totp.verify(totp.decrypt(t.secret_enc), code, t.last_step)
    if step is None:
        return None
    t.last_step = step
    return "totp"


@router.post("/mfa/verify")
async def mfa_verify(body: CodeIn, request: Request, p: Principal = Depends(staff_principal),
                     db: AsyncSession = Depends(get_db)):
    """Unlock the admin panel for this session (TOTP code or one backup code)."""
    await _limit(request, f"admin:mfa:{p.user.id}", 5)
    await _limit(request, f"admin:mfa-ip:{client_ip(request)}", 20)
    kind = await check_second_factor(db, p.user, body.code)
    if kind is None:
        audit(db, request, p.user, "mfa.verify.fail", target_type="user", target_id=p.user.id)
        await db.commit()
        raise HTTPException(422, "That code didn't work. Try the newest code from your app.")
    _unlock(p.session)
    audit(db, request, p.user, "mfa.verify", target_type="user", target_id=p.user.id, after={"method": kind}, full=True)
    await db.commit()
    await ratelimit.reset(_redis(request), get_settings().redis_prefix, f"admin:mfa:{p.user.id}")
    left = (await db.execute(select(BackupCode.id).where(BackupCode.user_id == p.user.id, BackupCode.used_at.is_(None)))).all()
    return {"ok": True, "method": kind, "backup_codes_left": len(left)}


@router.post("/mfa/backup-codes")
async def regenerate_backup_codes(request: Request, p: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    codes = await _new_backup_codes(db, p.user.id)
    audit(db, request, p.user, "mfa.backup_codes.regenerate", target_type="user", target_id=p.user.id)
    await db.commit()
    return {"backup_codes": codes}


# ── Step-up re-auth (password + 2FA, valid 10 min) ───────────────────────────
class StepUpIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=32)


@router.post("/stepup")
async def stepup(body: StepUpIn, request: Request, p: Principal = Depends(require_unlocked), db: AsyncSession = Depends(get_db)):
    await _limit(request, f"admin:stepup:{p.user.id}", 5)
    ok_pw = verify_password(p.user.password_hash, body.password)
    kind = await check_second_factor(db, p.user, body.code) if ok_pw else None
    if not ok_pw or kind is None:
        audit(db, request, p.user, "stepup.fail", target_type="user", target_id=p.user.id)
        await db.commit()
        raise HTTPException(422, "Password or 2FA code is incorrect")
    until = utcnow() + timedelta(minutes=get_settings().stepup_minutes)
    p.session.stepup_until = until
    audit(db, request, p.user, "stepup", target_type="user", target_id=p.user.id, after={"method": kind}, full=True)
    await db.commit()
    return {"stepup_until": iso(until)}


@router.post("/lock")
async def lock_now(request: Request, p: Principal = Depends(staff_principal), db: AsyncSession = Depends(get_db)):
    """Lock the admin panel on this device (the normal app session stays signed in)."""
    p.session.mfa_at = p.session.admin_seen_at = p.session.stepup_until = None
    audit(db, request, p.user, "admin.lock", target_type="user", target_id=p.user.id)
    await db.commit()
    return {"ok": True}


class SignOutAllIn(BaseModel):
    scope: str = Field("mine", pattern="^(mine|all_staff)$")


@router.post("/sessions/sign-out-admin")
async def sign_out_admin_sessions(body: SignOutAllIn, request: Request, p: Principal = Depends(require_unlocked),
                                  db: AsyncSession = Depends(get_db)):
    """Lock every admin session (yours, or every staff member's: owner only). The current one stays unlocked."""
    q = update(UserSession).values(mfa_at=None, admin_seen_at=None, stepup_until=None).where(UserSession.id != p.session.id)
    if body.scope == "all_staff":
        if not rbac.has(p.user.role, "roles.write"):
            raise HTTPException(403, "Only the owner can lock every staff session")
        from models import STAFF_ROLES
        staff_ids = select(User.id).where(User.role.in_(STAFF_ROLES))
        q = q.where(UserSession.user_id.in_(staff_ids))
    else:
        q = q.where(UserSession.user_id == p.user.id)
    n = (await db.execute(q)).rowcount or 0
    audit(db, request, p.user, "admin.sessions.sign_out", target_type="user", target_id=p.user.id,
          after={"scope": body.scope, "sessions": n}, full=True)
    await db.commit()
    return {"ok": True, "sessions": n}


# ── Audit log (read-only: there is no endpoint that edits or deletes it) ─────
def _audit_out(a: AdminAudit) -> dict:
    return {"id": a.id, "at": iso(a.at), "actor_id": a.actor_id, "actor_email": a.actor_email, "actor_role": a.actor_role,
            "action": a.action, "target_type": a.target_type, "target_id": a.target_id, "target_label": a.target_label,
            "before": a.before_json, "after": a.after_json, "reason": a.reason, "ip": a.ip, "user_agent": a.user_agent}


@router.get("/audit")
async def audit_list(request: Request, lp: ListParams = Depends(), actor: str = Query("", max_length=254),
                     action: str = Query("", max_length=64), target_type: str = Query("", max_length=32),
                     target_id: str = Query("", max_length=64), since: str = Query("", max_length=32),
                     until: str = Query("", max_length=32),
                     p: Principal = Depends(require_perm("audit.read")), db: AsyncSession = Depends(get_db)):
    from datetime import datetime
    stmt = select(AdminAudit)
    if actor:
        stmt = stmt.where(AdminAudit.actor_id == int(actor)) if actor.isdigit() else stmt.where(AdminAudit.actor_email.contains(actor.lower()))
    if action:
        stmt = stmt.where(AdminAudit.action.startswith(action))
    if target_type:
        stmt = stmt.where(AdminAudit.target_type == target_type)
    if target_id:
        stmt = stmt.where(AdminAudit.target_id == target_id)
    for val, op in ((since, "ge"), (until, "lt")):
        if val:
            try:
                d = datetime.fromisoformat(val.replace("Z", ""))
            except ValueError as e:
                raise HTTPException(422, "Dates look like 2026-11-24") from e
            stmt = stmt.where(AdminAudit.at >= d if op == "ge" else AdminAudit.at < d)
    if lp.q:
        like = f"%{lp.q}%"
        stmt = stmt.where(AdminAudit.action.like(like) | AdminAudit.target_label.like(like) | AdminAudit.reason.like(like))
    return await respond(db, request, p, stmt, lp, sorts={"at": AdminAudit.at, "action": AdminAudit.action,
                                                          "actor": AdminAudit.actor_email},
                         default_sort=AdminAudit.id.desc(), row=_audit_out, name="audit")


# ── Security settings: admin IP allowlist (off by default; the owner's IP changes) ──
class AllowlistIn(BaseModel):
    enabled: bool
    cidrs: list[str] = Field(default_factory=list, max_length=50)


@router.get("/settings/security")
async def get_security(request: Request, p: Principal = Depends(require_perm("settings.read")), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    return {"ip_allowlist": await settings_store.get(db, "security.admin_ip_allowlist"), "your_ip": client_ip(request),
            "idle_minutes": s.admin_idle_minutes, "stepup_minutes": s.stepup_minutes,
            "session_days": s.session_days, "impersonate_minutes": s.impersonate_minutes}


@router.put("/settings/security")
async def put_security(body: AllowlistIn, request: Request, p: Principal = Depends(require_perm("settings.write")),
                       _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    import ipaddress
    cidrs = []
    for c in body.cidrs:
        try:
            cidrs.append(str(ipaddress.ip_network(c.strip(), strict=False)))
        except ValueError as e:
            raise HTTPException(422, f"Not an IP address or range: {c}") from e
    if body.enabled and not ip_allowed(client_ip(request), cidrs):
        raise HTTPException(422, "Your current IP isn't in the list; saving would lock you out")
    before = await settings_store.get(db, "security.admin_ip_allowlist")
    after = {"enabled": body.enabled, "cidrs": cidrs}
    await settings_store.put(db, "security.admin_ip_allowlist", after, p.user.id)
    audit(db, request, p.user, "settings.security.ip_allowlist", target_type="setting",
          target_id="security.admin_ip_allowlist", before=before, after=after)
    await db.commit()
    return {"ip_allowlist": after}

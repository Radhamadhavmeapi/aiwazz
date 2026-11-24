"""/api/auth/* (csrf, signup, login, logout, me) and /api/keys (API key management)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, utcnow
from models import ApiKey, Invite, User, UserSession
from settings import get_settings

from . import ratelimit
from mailer import notify_support
from .deps import Principal, client_ip, csrf_protect, current_principal, optional_principal
from .security import (
    hash_password,
    needs_rehash,
    new_api_key,
    new_token,
    normalize_invite,
    password_problem,
    sha256,
    verify_password,
)

router = APIRouter(prefix="/api")
WINDOW_LOGIN = 15 * 60
WINDOW_SIGNUP = 60 * 60


def _redis(request: Request):
    return request.app.state.redis


def me_payload(u: User, via: str = "session", p: Principal | None = None) -> dict:
    from usage import has_api_access
    out = {"id": u.id, "email": u.email, "role": u.role, "plan": u.effective_plan,
           "plan_until": u.plan_until.isoformat() + "Z" if u.plan_until and u.effective_plan != "free" else None, "api_access": has_api_access(u),
           "created_at": u.created_at.isoformat() + "Z", "via": via, "staff": u.is_staff}
    if p is not None and p.impersonator is not None:
        out["impersonation"] = {"by": p.impersonator.email, "until": p.session.impersonate_until.isoformat() + "Z"}
        out["staff"] = False
    return out


def _set_cookie(resp: Response, name: str, value: str, max_age: int, http_only: bool) -> None:
    s = get_settings()
    resp.set_cookie(name, value, max_age=max_age, path="/", secure=s.cookie_secure, httponly=http_only, samesite="lax")


def _ensure_csrf(request: Request, resp: Response) -> str:
    s = get_settings()
    token = request.cookies.get(s.csrf_cookie) or new_token()
    _set_cookie(resp, s.csrf_cookie, token, max_age=s.session_days * 86400, http_only=False)
    return token


async def _start_session(db: AsyncSession, request: Request, resp: Response, user: User) -> None:
    s = get_settings()
    token = new_token()
    now = utcnow()
    db.add(
        UserSession(
            token_hash=sha256(token),
            user_id=user.id,
            expires_at=now + timedelta(days=s.session_days),
            last_seen_at=now,
            ip=client_ip(request)[:45],
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    user.last_login_at = now
    await db.commit()
    _set_cookie(resp, s.session_cookie, token, max_age=s.session_days * 86400, http_only=True)
    # Fresh CSRF token per session (session fixation / token rotation).
    _set_cookie(resp, s.csrf_cookie, new_token(), max_age=s.session_days * 86400, http_only=False)


def _too_many(retry_after: int) -> HTTPException:
    mins = max(1, round(retry_after / 60))
    return HTTPException(429, f"Too many attempts. Try again in {mins} minute{'s' if mins > 1 else ''}.",
                         headers={"Retry-After": str(retry_after)})


# ── CSRF bootstrap ────────────────────────────────────────────────────────────
@router.get("/auth/csrf")
async def csrf(request: Request, response: Response):
    """Sets the CSRF cookie (readable by JS) and returns the token to echo in X-CSRF-Token."""
    return {"csrf_token": _ensure_csrf(request, response)}


# ── Signup (invite-only) ─────────────────────────────────────────────────────
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    invite_code: str = Field(default="", max_length=32)   # required unless signup mode is "open" (admin → Settings)
    accept_terms: bool = False          # Terms, Privacy Policy and Acceptable Use Policy (required)
    marketing_opt_in: bool = False      # product updates (optional)


@router.post("/auth/signup", status_code=201, dependencies=[Depends(csrf_protect)])
async def signup(body: SignupIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"signup:ip:{client_ip(request)}", s.signup_max_per_ip, WINDOW_SIGNUP)
    if not lim.allowed:
        raise _too_many(lim.retry_after)

    if not body.accept_terms:
        raise HTTPException(422, "Please accept the Terms, Privacy Policy and Acceptable Use Policy to continue")
    email = body.email.lower().strip()
    if problem := password_problem(body.password, email, s.password_min_length):
        raise HTTPException(422, problem)

    from admin import settings_store
    mode = (await settings_store.get(db, "general"))["signup_mode"]
    if mode == "closed":
        raise HTTPException(403, "New signups are paused right now. Please check back soon.")
    if await _blocked(db, email, client_ip(request)):
        raise HTTPException(422, "We can't create an account with these details. Contact support@aiwazz.in.")
    now = utcnow()
    invite = None
    if body.invite_code.strip() or mode != "open":
        invite = (await db.execute(select(Invite).where(Invite.code_hash == sha256(normalize_invite(body.invite_code))))).scalar_one_or_none()
        if not invite or invite.revoked or invite.uses >= invite.max_uses or (invite.expires_at and invite.expires_at <= now):
            raise HTTPException(422, "This invite code isn't valid or has already been used")
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")

    if invite is not None:
        # Claim one use atomically (two signups racing for the last use: only one wins).
        claimed = await db.execute(
            update(Invite).where(Invite.id == invite.id, Invite.uses < Invite.max_uses).values(uses=Invite.uses + 1)
        )
        if claimed.rowcount != 1:
            await db.rollback()
            raise HTTPException(422, "This invite code isn't valid or has already been used")
    role = invite.role if invite is not None and invite.role != "owner" else "user"
    user = User(email=email, password_hash=hash_password(body.password), role=role,
                consent_at=now, terms_version=s.terms_version, consent_ip=client_ip(request)[:45],
                marketing_opt_in=body.marketing_opt_in)
    if invite is not None and invite.plan and invite.plan != "free" and (invite.plan_until is None or invite.plan_until > now):
        user.plan, user.plan_until = invite.plan, invite.plan_until
    db.add(user)
    await db.flush()
    await _start_session(db, request, response, user)
    return me_payload(user)


async def _blocked(db: AsyncSession, email: str, ip: str) -> bool:
    """Moderation blocklist (admin → Moderation): emails, email domains and IPs (filled in A4)."""
    try:
        from admin.moderation import is_blocked
    except ImportError:
        return False
    return await is_blocked(db, email=email, ip=ip)


# ── Login / logout / me ──────────────────────────────────────────────────────
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login", dependencies=[Depends(csrf_protect)])
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    r = _redis(request)
    email = body.email.lower().strip()
    ip = client_ip(request)
    for key, limit in ((f"login:ip:{ip}", s.login_max_per_ip), (f"login:email:{sha256(email)}", s.login_max_per_email)):
        lim = await ratelimit.hit(r, s.redis_prefix, key, limit, WINDOW_LOGIN)
        if not lim.allowed:
            raise _too_many(lim.retry_after)

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = verify_password(user.password_hash if user else None, body.password)
    if not user or not ok or not user.is_active:
        raise HTTPException(401, "Incorrect email or password")
    if user.suspended_at:
        from .deps import SUSPENDED_MSG
        raise HTTPException(403, SUSPENDED_MSG)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    await ratelimit.reset(r, s.redis_prefix, f"login:email:{sha256(email)}")
    await _start_session(db, request, response, user)
    return me_payload(user)


@router.post("/auth/logout", dependencies=[Depends(csrf_protect)])
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    token = request.cookies.get(s.session_cookie)
    if token:
        sess = (await db.execute(select(UserSession).where(UserSession.token_hash == sha256(token)))).scalar_one_or_none()
        if sess:
            await db.delete(sess)
            await db.commit()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(s.session_cookie, path="/", secure=s.cookie_secure, httponly=True, samesite="lax")
    return resp


@router.get("/auth/session")
async def session(p: Principal | None = Depends(optional_principal)):
    """Like /auth/me but always 200 ({"user": null} when signed out), so the app's first check is quiet."""
    return {"user": me_payload(p.user, p.via, p) if p else None}


@router.get("/auth/me")
async def me(p: Principal = Depends(current_principal)):
    return me_payload(p.user, p.via, p)


# ── API keys ─────────────────────────────────────────────────────────────────
def _key_out(k: ApiKey) -> dict:
    iso = lambda d: d.isoformat() + "Z" if d else None  # noqa: E731
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": iso(k.created_at),
            "last_used_at": iso(k.last_used_at), "revoked": k.revoked_at is not None}


def _session_only(p: Principal = Depends(current_principal)) -> Principal:
    if p.via != "session":
        raise HTTPException(403, "Manage API keys from the dashboard")
    return p


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("/keys")
async def list_keys(p: Principal = Depends(_session_only), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ApiKey).where(ApiKey.user_id == p.user.id, ApiKey.revoked_at.is_(None))
                             .order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"keys": [_key_out(k) for k in rows]}


@router.post("/keys", status_code=201, dependencies=[Depends(csrf_protect)])
async def create_key(body: KeyIn, p: Principal = Depends(_session_only), db: AsyncSession = Depends(get_db)):
    from usage import has_api_access
    if not has_api_access(p.user):
        raise HTTPException(403, "API access is included in the Creator and Pro plans")
    active = (await db.execute(select(ApiKey.id).where(ApiKey.user_id == p.user.id, ApiKey.revoked_at.is_(None)))).all()
    if len(active) >= 10:
        raise HTTPException(422, "You can have up to 10 active API keys. Revoke one first.")
    raw = new_api_key()
    key = ApiKey(user_id=p.user.id, name=body.name.strip(), prefix=raw[:13], key_hash=sha256(raw))
    db.add(key)
    await db.commit()
    return _key_out(key) | {"key": raw}  # the only time the full key is returned


@router.delete("/keys/{key_id}", dependencies=[Depends(csrf_protect)])
async def revoke_key(key_id: int, p: Principal = Depends(_session_only), db: AsyncSession = Depends(get_db)):
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == p.user.id))).scalar_one_or_none()
    if not key or key.revoked_at:
        raise HTTPException(404, "API key not found")
    key.revoked_at = utcnow()
    await db.commit()
    return {"ok": True}


# ── Account: change password, sign out other devices ─────────────────────────
class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


async def _drop_other_sessions(db: AsyncSession, p: Principal) -> int:
    from sqlalchemy import delete
    q = delete(UserSession).where(UserSession.user_id == p.user.id)
    if p.session is not None:
        q = q.where(UserSession.id != p.session.id)
    return (await db.execute(q)).rowcount or 0


@router.post("/auth/password", dependencies=[Depends(csrf_protect)])
async def change_password(body: PasswordIn, request: Request, p: Principal = Depends(_session_only), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"pw:user:{p.user.id}", 5, WINDOW_LOGIN)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    user = await db.get(User, p.user.id)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(422, "Your current password is incorrect")
    if problem := password_problem(body.new_password, user.email, s.password_min_length):
        raise HTTPException(422, problem)
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a password you haven't used here")
    user.password_hash = hash_password(body.new_password)
    signed_out = await _drop_other_sessions(db, p)
    await db.commit()
    return {"ok": True, "signed_out_sessions": signed_out}


@router.post("/auth/logout-others", dependencies=[Depends(csrf_protect)])
async def logout_others(p: Principal = Depends(_session_only), db: AsyncSession = Depends(get_db)):
    n = await _drop_other_sessions(db, p)
    await db.commit()
    return {"ok": True, "signed_out_sessions": n}


# ── Account deletion ─────────────────────────────────────────────────────────
class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirm: str = Field(min_length=1, max_length=16)  # must be "DELETE"


@router.post("/auth/delete-account", dependencies=[Depends(csrf_protect)])
async def delete_account(body: DeleteAccountIn, request: Request, p: Principal = Depends(_session_only),
                         db: AsyncSession = Depends(get_db)):
    """Permanently deletes the account, its sessions, API keys, history and audio files."""
    from sqlalchemy import func

    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"del:user:{p.user.id}", 5, WINDOW_LOGIN)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    if body.confirm != "DELETE":
        raise HTTPException(422, 'Type DELETE to confirm')
    user = await db.get(User, p.user.id)
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(422, "Your password is incorrect")
    if user.role == "owner":
        raise HTTPException(422, "You're the owner. Transfer ownership to another admin first (Admin → Team & roles).")
    if user.role == "admin":
        admins = (await db.execute(select(func.count()).select_from(User)
                                   .where(User.role.in_(("owner", "admin")), User.is_active.is_(True)))).scalar_one()
        if admins <= 1:
            raise HTTPException(422, "You're the only admin. Make another admin first, so nobody gets locked out.")

    # Stop future charges first (fails the request if Razorpay can't be reached, so nobody is charged after deleting).
    from accounts import delete_user_data
    from billing.routes import cancel_for_account_deletion
    await cancel_for_account_deletion(db, user.id)
    reference, n_gen = await delete_user_data(db, user)
    await db.commit()

    resp = JSONResponse({"ok": True, "deleted_generations": n_gen, "reference": reference})
    resp.delete_cookie(s.session_cookie, path="/", secure=s.cookie_secure, httponly=True, samesite="lax")
    return resp



# ── Contact form (aiwazz.in/contact/, proxied same-origin by nginx) ────────────
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=10, max_length=4000)
    consent: bool = False
    website: str = ""   # honeypot: real people never fill this hidden field


@router.post("/contact", status_code=201)
async def contact(body: ContactIn, request: Request, db: AsyncSession = Depends(get_db)):
    from models import ContactMessage

    s = get_settings()
    if (request.headers.get("origin") or "") not in s.contact_origins:
        raise HTTPException(403, "Request blocked (origin)")
    if body.website:                       # bot: pretend success, store nothing
        return {"ok": True}
    if not body.consent:
        raise HTTPException(422, "Please allow us to use your details to reply")
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"contact:ip:{client_ip(request)}", s.contact_max_per_ip, 3600)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    db.add(ContactMessage(name=body.name.strip(), email=body.email.lower(), subject=body.subject.strip(),
                          message=body.message.strip(), ip=client_ip(request)[:45]))
    await db.commit()
    await notify_support(request, "contact", {"name": body.name.strip(), "email": body.email.lower(),
                                              "subject": body.subject.strip(), "message": body.message.strip()})
    return {"ok": True}


# ── "Request an invite" (signup page on login.aiwazz.in, session-less but CSRF + Origin checked) ──
class InviteRequestIn(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=100)
    use_case: str = Field(default="", max_length=500)
    website: str = ""   # honeypot


@router.post("/auth/invite-request", status_code=202, dependencies=[Depends(csrf_protect)])
async def invite_request(body: InviteRequestIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Same answer for new, repeated or already-registered emails (no account enumeration)."""
    from models import InviteRequest

    if body.website:
        return {"ok": True}
    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"invreq:ip:{client_ip(request)}", s.invite_request_max_per_ip, 3600)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    email = body.email.lower()
    row = (await db.execute(select(InviteRequest).where(InviteRequest.email == email))).scalar_one_or_none()
    if row is None:
        row = InviteRequest(email=email)
        db.add(row)
    row.name, row.use_case = body.name.strip(), body.use_case.strip()
    row.ip, row.updated_at = client_ip(request)[:45], utcnow()
    await db.commit()
    await notify_support(request, "invite_request", {"email": email, "name": row.name, "use_case": row.use_case})
    return {"ok": True}


# ── Password reset (link emailed by staff from the admin panel; self-service "forgot password" comes later) ──
class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/auth/reset-password", dependencies=[Depends(csrf_protect)])
async def reset_password(body: ResetIn, request: Request, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete

    from models import PasswordReset
    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"reset:ip:{client_ip(request)}", 10, 3600)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    row = (await db.execute(select(PasswordReset).where(PasswordReset.token_hash == sha256(body.token)))).scalar_one_or_none()
    if row is None or row.used_at or row.expires_at <= utcnow():
        raise HTTPException(422, "This reset link has expired or was already used. Ask support for a new one.")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(422, "This reset link has expired or was already used. Ask support for a new one.")
    if problem := password_problem(body.new_password, user.email, s.password_min_length):
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    row.used_at = utcnow()
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.commit()
    return {"ok": True}

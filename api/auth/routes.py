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
from .deps import Principal, client_ip, csrf_protect, current_principal
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


def me_payload(u: User, via: str = "session") -> dict:
    from usage import has_api_access
    return {"id": u.id, "email": u.email, "role": u.role, "plan": u.plan or "free", "api_access": has_api_access(u),
            "created_at": u.created_at.isoformat() + "Z", "via": via}


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
    invite_code: str = Field(min_length=4, max_length=32)
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

    now = utcnow()
    invite = (await db.execute(select(Invite).where(Invite.code_hash == sha256(normalize_invite(body.invite_code))))).scalar_one_or_none()
    if not invite or invite.revoked or invite.uses >= invite.max_uses or (invite.expires_at and invite.expires_at <= now):
        raise HTTPException(422, "This invite code isn't valid or has already been used")
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")

    # Claim one use atomically (two signups racing for the last use: only one wins).
    claimed = await db.execute(
        update(Invite).where(Invite.id == invite.id, Invite.uses < Invite.max_uses).values(uses=Invite.uses + 1)
    )
    if claimed.rowcount != 1:
        await db.rollback()
        raise HTTPException(422, "This invite code isn't valid or has already been used")
    user = User(email=email, password_hash=hash_password(body.password), role=invite.role,
                consent_at=now, terms_version=s.terms_version, consent_ip=client_ip(request)[:45],
                marketing_opt_in=body.marketing_opt_in)
    db.add(user)
    await db.flush()
    await _start_session(db, request, response, user)
    return me_payload(user)


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


@router.get("/auth/me")
async def me(p: Principal = Depends(current_principal)):
    return me_payload(p.user, p.via)


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
    from sqlalchemy import delete, func

    import secrets as _secrets

    from models import DeletionLog, Generation

    s = get_settings()
    lim = await ratelimit.hit(_redis(request), s.redis_prefix, f"del:user:{p.user.id}", 5, WINDOW_LOGIN)
    if not lim.allowed:
        raise _too_many(lim.retry_after)
    if body.confirm != "DELETE":
        raise HTTPException(422, 'Type DELETE to confirm')
    user = await db.get(User, p.user.id)
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(422, "Your password is incorrect")
    if user.role == "admin":
        admins = (await db.execute(select(func.count()).select_from(User)
                                   .where(User.role == "admin", User.is_active.is_(True)))).scalar_one()
        if admins <= 1:
            raise HTTPException(422, "You're the only admin. Make another admin first, so nobody gets locked out.")

    gen_ids = (await db.execute(select(Generation.id).where(Generation.user_id == user.id))).scalars().all()
    audio_dir = request.app.state.jobs.s.audio_dir
    for gid in gen_ids:
        for ext in ("mp3", "wav", "json"):
            (audio_dir / f"{gid}.{ext}").unlink(missing_ok=True)
    # Explicit deletes (portable; doesn't rely on FK cascades)
    await db.execute(delete(Generation).where(Generation.user_id == user.id))
    await db.execute(delete(ApiKey).where(ApiKey.user_id == user.id))
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.execute(update(Invite).where(Invite.created_by == user.id).values(created_by=None))
    reference = f"DEL-{utcnow():%Y%m%d}-{_secrets.token_hex(3).upper()}"
    db.add(DeletionLog(reference=reference, email_hash=sha256(user.email), generations_deleted=len(gen_ids)))
    await db.delete(user)
    await db.commit()

    resp = JSONResponse({"ok": True, "deleted_generations": len(gen_ids), "reference": reference})
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
    return {"ok": True}

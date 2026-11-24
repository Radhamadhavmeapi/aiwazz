"""Request dependencies: who is calling (session cookie or X-API-Key), CSRF + Origin checks, roles."""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, utcnow
from models import ApiKey, User, UserSession
from settings import get_settings

from .security import API_KEY_PREFIX, same, sha256

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    user: User
    via: str                      # "session" | "api_key"
    session: UserSession | None = None
    api_key: ApiKey | None = None
    impersonator: User | None = None   # staff member viewing as this user (read-only, admin panel)

    @property
    def read_only(self) -> bool:
        return self.impersonator is not None


# While impersonating, only these writes are allowed (everything else is a read-only view).
IMPERSONATION_WRITES = {"/api/admin/impersonate/stop", "/api/auth/logout"}
SUSPENDED_MSG = "Your account is paused. If you think this is a mistake, write to support@aiwazz.in."


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers (trusted: 127.0.0.1 only) puts the X-Forwarded-For client here.
    return request.client.host if request.client else "unknown"


async def _from_api_key(db: AsyncSession, raw: str) -> Principal | None:
    if not raw.startswith(API_KEY_PREFIX) or len(raw) > 100:
        return None
    key = (await db.execute(select(ApiKey).where(ApiKey.key_hash == sha256(raw)))).scalar_one_or_none()
    if not key or key.revoked_at or not key.user.is_active:
        return None
    if key.user.suspended_at:
        raise HTTPException(403, SUSPENDED_MSG)
    from usage import has_api_access
    if not has_api_access(key.user):
        raise HTTPException(403, "API access is included in the Creator and Pro plans")
    now = utcnow()
    if not key.last_used_at or now - key.last_used_at > timedelta(minutes=5):
        key.last_used_at = now
        await db.commit()
    return Principal(user=key.user, via="api_key", api_key=key)


async def _from_session(db: AsyncSession, token: str) -> Principal | None:
    if not token or len(token) > 100:
        return None
    sess = (await db.execute(select(UserSession).where(UserSession.token_hash == sha256(token)))).scalar_one_or_none()
    now = utcnow()
    if not sess or sess.expires_at <= now or not sess.user.is_active or sess.user.suspended_at:
        return None
    if now - sess.last_seen_at > timedelta(minutes=5):
        sess.last_seen_at = now
        if not sess.user.last_active_at or now - sess.user.last_active_at > timedelta(minutes=5):
            sess.user.last_active_at = now
        await db.commit()
    if sess.impersonate_user_id:
        target = await db.get(User, sess.impersonate_user_id) if sess.impersonate_until and sess.impersonate_until > now else None
        if target is None or not sess.user.is_staff:
            sess.impersonate_user_id = sess.impersonate_until = None   # expired: back to the staff member's own view
            await db.commit()
        else:
            return Principal(user=target, via="session", session=sess, impersonator=sess.user)
    return Principal(user=sess.user, via="session", session=sess)


async def optional_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal | None:
    s = get_settings()
    raw_key = request.headers.get("x-api-key")
    if raw_key is not None:
        p = await _from_api_key(db, raw_key.strip())
        if p is None:
            raise HTTPException(401, "Invalid API key")
        return p
    p = await _from_session(db, request.cookies.get(s.session_cookie, ""))
    if p and p.read_only and request.method in UNSAFE and request.url.path not in IMPERSONATION_WRITES:
        raise HTTPException(403, "Read-only view: you're viewing this account as staff. Stop viewing to make changes.")
    return p


async def current_principal(p: Principal | None = Depends(optional_principal)) -> Principal:
    if p is None:
        raise HTTPException(401, "Sign in to continue")
    return p


async def require_admin(p: Principal = Depends(current_principal)) -> Principal:
    if not p.user.is_admin:
        raise HTTPException(403, "Admins only")
    return p


def csrf_protect(request: Request) -> None:
    """Cookie-authenticated writes need (1) an allowed Origin and (2) X-CSRF-Token matching the CSRF cookie
    (double submit; the __Host- cookie can't be set by other subdomains). API-key calls carry no cookies
    and are exempt."""
    if request.method not in UNSAFE:
        return
    if "x-api-key" in request.headers and not request.cookies:
        return
    s = get_settings()
    origin = request.headers.get("origin") or ""
    if not origin:
        referer = request.headers.get("referer") or ""
        origin = "/".join(referer.split("/")[:3]) if referer else ""
    if origin not in s.allowed_origins:
        raise HTTPException(403, "Request blocked (origin)")
    cookie = request.cookies.get(s.csrf_cookie, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not same(cookie, header):
        raise HTTPException(403, "Request blocked (CSRF). Reload the page and try again.")

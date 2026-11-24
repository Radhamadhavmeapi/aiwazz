"""Admin request guards. Order on every /api/admin route:
staff_principal (non-staff, API keys, IP not allowed → plain 404; rate limit) → CSRF/Origin on writes →
require_unlocked (2FA set up AND verified for this session, idle ≤ 30 min) → require_perm(...) → require_stepup."""
import ipaddress
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import ratelimit
from auth.deps import Principal, client_ip, optional_principal
from db import get_db, utcnow
from models import TotpSecret
from settings import get_settings

from . import rbac, settings_store

NOT_FOUND = HTTPException(404, "Not Found")      # identical to FastAPI's own 404 for unknown routes


def ip_allowed(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for c in cidrs:
        try:
            if addr in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            continue
    return False


async def staff_principal(request: Request, p: Principal | None = Depends(optional_principal),
                          db: AsyncSession = Depends(get_db)) -> Principal:
    if p is None or p.via != "session" or p.session is None or not p.user.is_staff or p.session.impersonate_user_id:
        raise NOT_FOUND
    allow = await settings_store.get(db, "security.admin_ip_allowlist")
    if allow.get("enabled") and not ip_allowed(client_ip(request), allow.get("cidrs") or []):
        raise NOT_FOUND
    s = get_settings()
    lim = await ratelimit.hit(request.app.state.redis, s.redis_prefix, f"admin:user:{p.user.id}", s.admin_rate_per_5min, 300)
    if not lim.allowed:
        raise HTTPException(429, "Too many admin requests. Wait a moment.", headers={"Retry-After": str(lim.retry_after)})
    return p


def lock(reason: str) -> HTTPException:
    msg = {"setup": "Set up two-factor authentication to open the admin panel",
           "verify": "Enter your 2FA code to unlock the admin panel"}[reason]
    return HTTPException(401, msg, headers={"X-Admin-Lock": reason})


def unlocked_state(p: Principal) -> bool:
    s, sess, now = get_settings(), p.session, utcnow()
    if sess is None or sess.mfa_at is None or sess.admin_seen_at is None:
        return False
    return (now - sess.admin_seen_at <= timedelta(minutes=s.admin_idle_minutes)
            and now - sess.mfa_at <= timedelta(hours=s.admin_max_hours))


async def require_unlocked(p: Principal = Depends(staff_principal), db: AsyncSession = Depends(get_db)) -> Principal:
    totp = await db.get(TotpSecret, p.user.id)
    if totp is None or totp.enabled_at is None:
        raise lock("setup")
    if not unlocked_state(p):
        raise lock("verify")
    now = utcnow()
    if now - p.session.admin_seen_at > timedelta(seconds=30):
        p.session.admin_seen_at = now
        await db.commit()
    return p


def require_perm(*perms: str):
    unknown = set(perms) - rbac.PERMS
    assert not unknown, f"unknown permission(s): {unknown}"

    async def dep(p: Principal = Depends(require_unlocked)) -> Principal:
        if not all(rbac.has(p.user.role, x) for x in perms):
            raise HTTPException(403, "Your role doesn't allow this")
        return p
    dep.perms = frozenset(perms)      # read by the permission-matrix test
    return dep


def stepup_ok(p: Principal) -> bool:
    return bool(p.session and p.session.stepup_until and p.session.stepup_until > utcnow())


async def require_stepup(p: Principal = Depends(require_unlocked)) -> Principal:
    if not stepup_ok(p):
        raise HTTPException(403, "Confirm it's you (password + 2FA code) to continue", headers={"X-Step-Up": "required"})
    return p

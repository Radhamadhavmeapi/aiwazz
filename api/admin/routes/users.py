"""A2: Users — list, detail tabs, actions (plan, bonus, suspend, password reset, sessions, keys, notes, tags, export,
delete, read-only impersonation) and bulk actions. Every write is audited; content is hidden behind the privacy rule."""
import json
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect, optional_principal
from auth.security import sha256
from db import get_db, utcnow
from models import (STAFF_ROLES, ApiKey, BonusGrant, Generation, Invoice, PasswordReset, Payment, Pronunciation,
                    Subscription, User, UserNote, UserSession, UserTag)
from settings import get_settings
from usage import PLANS, get_usage, period_bounds

from .. import rbac
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
IST = timedelta(hours=5, minutes=30)
REVEAL_REASONS = {"abuse_report": "Abuse report", "support_consent": "Support request with the user's consent",
                  "legal_request": "Legal request"}
REVEAL_TTL = 600


def status_of(u: User) -> str:
    return "suspended" if u.suspended_at else ("active" if u.is_active else "disabled")


def end_of_ist_day(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()) + timedelta(days=1) - IST


async def get_user(db: AsyncSession, uid: int) -> User:
    u = await db.get(User, uid)
    if u is None:
        raise HTTPException(404, "User not found")
    return u


def _guard_staff_target(p: Principal, u: User) -> None:
    """Changing another staff member's account is a role decision: owner only (and never the owner account itself)."""
    if u.role == "owner" and p.user.id != u.id:
        raise HTTPException(403, "The owner account can only be changed by the owner")
    if u.is_staff and u.id != p.user.id and not rbac.has(p.user.role, "roles.write"):
        raise HTTPException(403, "Only the owner can change staff accounts")


def _snapshot(u: User) -> dict:
    return {"plan": u.plan, "plan_until": iso(u.plan_until), "role": u.role, "is_active": u.is_active,
            "suspended": bool(u.suspended_at), "name": u.name}


# ── List ─────────────────────────────────────────────────────────────────────
def _list_stmt():
    start, _ = period_bounds()
    chars = (select(func.coalesce(func.sum(Generation.text_chars), 0))
             .where(Generation.user_id == User.id, Generation.status == "done", Generation.created_at >= start)
             .correlate(User).scalar_subquery())
    revenue = (select(func.coalesce(func.sum(Payment.amount_paise), 0))
               .where(Payment.user_id == User.id, Payment.status == "captured").correlate(User).scalar_subquery())
    refunded = _refunds_subquery()
    return select(User, chars.label("chars"), (revenue - refunded).label("revenue")), chars, revenue


def _refunds_subquery():
    try:
        from models import Refund
    except ImportError:
        from sqlalchemy import literal
        return literal(0)
    return (select(func.coalesce(func.sum(Refund.amount_paise), 0))
            .where(Refund.user_id == User.id, Refund.status == "processed").correlate(User).scalar_subquery())


async def _tags_for(db: AsyncSession, ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {i: [] for i in ids}
    if ids:
        for uid, tag in (await db.execute(select(UserTag.user_id, UserTag.tag).where(UserTag.user_id.in_(ids)).order_by(UserTag.tag))).all():
            out[uid].append(tag)
    return out


def _user_row(u: User, chars: int = 0, revenue: int = 0, tags: list[str] | None = None) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "plan": u.effective_plan, "plan_until": iso(u.plan_until),
            "status": status_of(u), "created_at": iso(u.created_at), "last_active_at": iso(u.last_active_at or u.last_login_at),
            "chars_this_month": int(chars or 0), "revenue_paise": int(revenue or 0), "tags": tags or []}


@router.get("/users")
async def list_users(request: Request, lp: ListParams = Depends(), plan: str = Query("", max_length=16),
                     status: str = Query("", max_length=16), role: str = Query("", max_length=16),
                     tag: str = Query("", max_length=32), p: Principal = Depends(require_perm("users.read")),
                     db: AsyncSession = Depends(get_db)):
    stmt, chars, revenue = _list_stmt()
    if lp.q:
        q = lp.q.lower()
        conds = [User.email.contains(q), User.name.contains(lp.q)]
        if q.isdigit():
            conds.append(User.id == int(q))
        stmt = stmt.where(or_(*conds))
    if plan:
        now = utcnow()
        stmt = stmt.where(or_(User.plan == "free", User.plan_until <= now)) if plan == "free" else \
            stmt.where(User.plan == plan, or_(User.plan_until.is_(None), User.plan_until > now))
    if status == "suspended":
        stmt = stmt.where(User.suspended_at.is_not(None))
    elif status == "active":
        stmt = stmt.where(User.suspended_at.is_(None), User.is_active.is_(True))
    elif status == "disabled":
        stmt = stmt.where(User.is_active.is_(False))
    if role == "staff":
        stmt = stmt.where(User.role.in_(STAFF_ROLES))
    elif role:
        stmt = stmt.where(User.role == role)
    if tag:
        stmt = stmt.where(User.id.in_(select(UserTag.user_id).where(UserTag.tag == tag.lower())))
    page = await respond(db, request, p, stmt, lp, scalars=False, name="users",
                         sorts={"created_at": User.created_at, "email": User.email, "last_active": User.last_active_at,
                                "chars": chars, "revenue": revenue, "plan": User.plan},
                         default_sort=User.id.desc(), row=lambda r: _user_row(r[0], r[1], r[2]))
    if isinstance(page, dict):
        tags = await _tags_for(db, [i["id"] for i in page["items"]])
        for i in page["items"]:
            i["tags"] = tags[i["id"]]
    return page


@router.get("/users/tags")
async def all_tags(p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(UserTag.tag, func.count()).group_by(UserTag.tag).order_by(UserTag.tag))).all()
    return {"items": [{"tag": t, "count": n} for t, n in rows]}


# ── Detail ───────────────────────────────────────────────────────────────────
async def _usage_history(db: AsyncSession, uid: int, months: int = 6) -> list[dict]:
    now = utcnow() + IST
    out = []
    y, m = now.year, now.month
    for _ in range(months):
        start = datetime(y, m, 1) - IST
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end = datetime(ny, nm, 1) - IST
        n = (await db.execute(select(func.coalesce(func.sum(Generation.text_chars), 0)).where(
            Generation.user_id == uid, Generation.status == "done", Generation.created_at >= start,
            Generation.created_at < end))).scalar_one()
        out.append({"month": f"{y}-{m:02d}", "chars": int(n)})
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(out))


@router.get("/users/{uid}")
async def user_detail(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    usage = await get_usage(db, u)
    start, end = usage.period_start, usage.period_end
    bonus = (await db.execute(select(BonusGrant).where(BonusGrant.user_id == uid).order_by(BonusGrant.id.desc()).limit(20))).scalars().all()
    tags = (await _tags_for(db, [uid]))[uid]
    gens = (await db.execute(select(func.count(), func.coalesce(func.sum(Generation.text_chars), 0))
                             .where(Generation.user_id == uid, Generation.status == "done"))).one()
    revenue = (await db.execute(select(func.coalesce(func.sum(Payment.amount_paise), 0))
                                .where(Payment.user_id == uid, Payment.status == "captured"))).scalar_one()
    return {
        "user": _user_row(u, usage.used, revenue, tags) | {
            "is_active": u.is_active, "suspended_at": iso(u.suspended_at), "suspend_reason": u.suspend_reason,
            "last_login_at": iso(u.last_login_at), "billing": {"name": u.billing_name, "gstin": u.billing_gstin,
                                                               "state": u.billing_state, "address": u.billing_address}},
        "usage": usage.to_dict(), "history": await _usage_history(db, uid),
        "bonus": [{"id": b.id, "chars": b.chars, "reason": b.reason, "created_at": iso(b.created_at),
                   "current": start <= b.period_start < end} for b in bonus],
        "lifetime": {"generations": int(gens[0]), "chars": int(gens[1]), "revenue_paise": int(revenue)},
        "consent": {"consent_at": iso(u.consent_at), "terms_version": u.terms_version, "consent_ip": u.consent_ip,
                    "marketing_opt_in": u.marketing_opt_in},
        "plans": [{"id": k, "name": v["name"], "characters": v["characters"]} for k, v in PLANS.items()],
        "can": {"write": rbac.has(p.user.role, "users.write"), "delete": rbac.has(p.user.role, "users.delete"),
                "impersonate": rbac.has(p.user.role, "users.impersonate"), "content": rbac.has(p.user.role, "users.content"),
                "export": rbac.has(p.user.role, "users.export")},
    }


@router.get("/users/{uid}/billing")
async def user_billing(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    await get_user(db, uid)
    subs = (await db.execute(select(Subscription).where(Subscription.user_id == uid).order_by(Subscription.id.desc()))).scalars().all()
    pays = (await db.execute(select(Payment).where(Payment.user_id == uid).order_by(Payment.id.desc()).limit(100))).scalars().all()
    invs = (await db.execute(select(Invoice).where(Invoice.user_id == uid).order_by(Invoice.id.desc()).limit(100))).scalars().all()
    return {
        "subscriptions": [{"id": s.id, "rzp_subscription_id": s.rzp_subscription_id, "plan": s.plan, "period": s.period,
                           "status": s.status, "current_start": iso(s.current_start), "current_end": iso(s.current_end),
                           "cancel_at_period_end": s.cancel_at_period_end, "created_at": iso(s.created_at)} for s in subs],
        "payments": [{"id": x.id, "rzp_payment_id": x.rzp_payment_id, "amount_paise": x.amount_paise, "status": x.status,
                      "method": x.method, "created_at": iso(x.created_at)} for x in pays],
        "invoices": [{"id": i.id, "number": i.number, "issued_at": iso(i.issued_at), "plan": i.plan, "period": i.period,
                      "total_paise": i.total_paise} for i in invs],
    }


def _gen_row(g: Generation) -> dict:
    return {"id": g.id, "status": g.status, "engine": g.engine, "voice": g.voice, "lang": g.lang, "style": g.style,
            "speed": g.speed, "chars": g.text_chars, "duration_sec": g.duration_sec, "compute_sec": g.compute_sec,
            "via": "api" if g.api_key_id else "web", "error": g.error, "created_at": iso(g.created_at),
            "finished_at": iso(g.finished_at)}


@router.get("/users/{uid}/generations")
async def user_generations(uid: int, request: Request, lp: ListParams = Depends(),
                           p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    """Metadata only. The script excerpt and audio need POST …/reveal (privacy rule)."""
    stmt = select(Generation).where(Generation.user_id == uid)
    return await respond(db, request, p, stmt, lp, sorts={"created_at": Generation.created_at, "chars": Generation.text_chars},
                         default_sort=Generation.created_at.desc(), row=_gen_row, name="generations")


class RevealIn(BaseModel):
    reason: str = Field(pattern="^(abuse_report|support_consent|legal_request)$")
    note: str = Field(default="", max_length=300)


@router.post("/generations/{gid}/reveal")
async def reveal_generation(gid: str, body: RevealIn, request: Request, p: Principal = Depends(require_perm("users.content")),
                            db: AsyncSession = Depends(get_db)):
    """Privacy rule: show a user's script excerpt + audio only with a stated reason; audited; audio link valid 10 min."""
    g = await db.get(Generation, gid)
    if g is None:
        raise HTTPException(404, "Not found")
    owner = await db.get(User, g.user_id)
    audit(db, request, p.user, "user.content.reveal", target_type="generation", target_id=g.id,
          label=owner.email if owner else "", reason=f"{REVEAL_REASONS[body.reason]}{': ' + body.note if body.note else ''}")
    await db.commit()
    s = get_settings()
    await request.app.state.redis.set(f"{s.redis_prefix}admin:reveal:{p.user.id}:{g.id}", "1", ex=REVEAL_TTL)
    jm = request.app.state.jobs
    has_audio = g.status == "done" and jm.audio_path(g.id, "mp3") is not None
    return {"excerpt": g.text_excerpt, "audio_url": f"/api/admin/generations/{g.id}/audio" if has_audio else None,
            "expires_in": REVEAL_TTL}


@router.get("/generations/{gid}/audio")
async def revealed_audio(gid: str, request: Request, p: Principal = Depends(require_perm("users.content"))):
    from fastapi.responses import FileResponse
    s = get_settings()
    if not await request.app.state.redis.get(f"{s.redis_prefix}admin:reveal:{p.user.id}:{gid}"):
        raise HTTPException(403, "Reveal this generation first (privacy rule: a reason is required)")
    path = request.app.state.jobs.audio_path(gid, "mp3")
    if path is None:
        raise HTTPException(410, "This audio was already deleted (kept 7 days)")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/users/{uid}/keys")
async def user_keys(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ApiKey).where(ApiKey.user_id == uid).order_by(ApiKey.id.desc()))).scalars().all()
    return {"items": [{"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": iso(k.created_at),
                       "last_used_at": iso(k.last_used_at), "revoked_at": iso(k.revoked_at)} for k in rows]}


@router.get("/users/{uid}/sessions")
async def user_sessions(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    now = utcnow()
    rows = (await db.execute(select(UserSession).where(UserSession.user_id == uid, UserSession.expires_at > now)
                             .order_by(UserSession.last_seen_at.desc()))).scalars().all()
    return {"items": [{"id": s.id, "created_at": iso(s.created_at), "last_seen_at": iso(s.last_seen_at), "ip": s.ip,
                       "user_agent": s.user_agent, "admin_unlocked": bool(s.mfa_at), "current": s.id == p.session.id}
                      for s in rows]}


@router.get("/users/{uid}/notes")
async def user_notes(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(UserNote).where(UserNote.user_id == uid).order_by(UserNote.id.desc()))).scalars().all()
    return {"items": [{"id": n.id, "body": n.body, "author_email": n.author_email, "created_at": iso(n.created_at),
                       "mine": n.author_id == p.user.id} for n in rows]}


@router.get("/users/{uid}/timeline")
async def user_timeline(uid: int, p: Principal = Depends(require_perm("users.read")), db: AsyncSession = Depends(get_db)):
    """Activity timeline from what we already record (no extra tracking): signup, logins, generations per day,
    payments, subscription changes and staff actions."""
    from models import AdminAudit
    u = await get_user(db, uid)
    ev: list[dict] = [{"at": iso(u.created_at), "kind": "signup", "text": "Signed up"}]
    if u.consent_at:
        ev.append({"at": iso(u.consent_at), "kind": "consent", "text": f"Accepted terms {u.terms_version or ''}".strip()})
    for s in (await db.execute(select(UserSession).where(UserSession.user_id == uid).order_by(UserSession.id.desc()).limit(20))).scalars():
        ev.append({"at": iso(s.created_at), "kind": "login", "text": f"Signed in from {s.ip or 'unknown IP'}"})
    day = func.date(Generation.created_at)
    for d, n, chars in (await db.execute(select(day, func.count(), func.sum(Generation.text_chars))
                                         .where(Generation.user_id == uid).group_by(day).order_by(day.desc()).limit(30))).all():
        ev.append({"at": f"{d}T12:00:00Z", "kind": "generation", "text": f"{n} generation{'s' if n != 1 else ''} · {int(chars or 0):,} characters"})
    for x in (await db.execute(select(Payment).where(Payment.user_id == uid).order_by(Payment.id.desc()).limit(20))).scalars():
        ev.append({"at": iso(x.created_at), "kind": "payment", "text": f"Payment ₹{x.amount_paise / 100:,.2f} {x.status}"})
    for sb in (await db.execute(select(Subscription).where(Subscription.user_id == uid).order_by(Subscription.id.desc()).limit(10))).scalars():
        ev.append({"at": iso(sb.created_at), "kind": "subscription", "text": f"Subscription {sb.plan} ({sb.period}) · now {sb.status}"})
    for a in (await db.execute(select(AdminAudit).where(AdminAudit.target_type == "user", AdminAudit.target_id == str(uid))
                               .order_by(AdminAudit.id.desc()).limit(30))).scalars():
        ev.append({"at": iso(a.at), "kind": "staff", "text": f"{a.action} by {a.actor_email}" + (f": {a.reason}" if a.reason else "")})
    ev.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"items": ev[:100]}


# ── Actions ──────────────────────────────────────────────────────────────────
class PlanIn(BaseModel):
    plan: str = Field(pattern="^(free|starter|creator|pro)$")
    until: date | None = None            # last day of the plan (IST); None = no end date
    reason: str = Field(min_length=3, max_length=255)
    notify: bool = False


@router.put("/users/{uid}/plan")
async def change_plan(uid: int, body: PlanIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    _guard_staff_target(p, u)
    if body.until and body.plan == "free":
        raise HTTPException(422, "An end date only makes sense with a paid plan")
    if body.until and body.until < (utcnow() + IST).date():
        raise HTTPException(422, "The end date is in the past")
    before = _snapshot(u)
    u.plan, u.plan_until = body.plan, end_of_ist_day(body.until) if body.until else None
    audit(db, request, p.user, "user.plan.change", target_type="user", target_id=u.id, label=u.email,
          before=before, after=_snapshot(u), reason=body.reason)
    if body.notify:
        from emails import send_template
        await send_template(db, "plan_changed", u.email, {"name": u.name or u.email.split("@")[0], "plan": PLANS[body.plan]["name"],
                            "until_note": f" until {body.until:%d %b %Y}" if body.until else ""}, user_id=u.id)
    await db.commit()
    return {"ok": True, "user": _user_row(u)}


class BonusIn(BaseModel):
    chars: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/users/{uid}/bonus")
async def add_bonus(uid: int, body: BonusIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                    db: AsyncSession = Depends(get_db)):
    if body.chars == 0:
        raise HTTPException(422, "Enter a number of characters (negative removes)")
    u = await get_user(db, uid)
    usage = await get_usage(db, u)
    db.add(BonusGrant(user_id=u.id, chars=body.chars, period_start=usage.period_start, reason=body.reason, granted_by=p.user.id))
    audit(db, request, p.user, "user.bonus", target_type="user", target_id=u.id, label=u.email,
          after={"chars": body.chars, "cycle_start": iso(usage.period_start)}, reason=body.reason, full=True)
    await db.commit()
    return {"ok": True, "usage": (await get_usage(db, u)).to_dict()}


class SuspendIn(BaseModel):
    suspend: bool
    reason: str = Field(min_length=3, max_length=255)       # internal
    message: str = Field(default="", max_length=500)         # optional note in the email to the user
    notify: bool = True


@router.post("/users/{uid}/suspend")
async def suspend(uid: int, body: SuspendIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                  db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    _guard_staff_target(p, u)
    if u.id == p.user.id:
        raise HTTPException(422, "You can't suspend your own account")
    before = _snapshot(u)
    if body.suspend:
        u.suspended_at, u.suspend_reason = utcnow(), body.reason
        await db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    else:
        u.suspended_at, u.suspend_reason = None, ""
    audit(db, request, p.user, "user.suspend" if body.suspend else "user.unsuspend", target_type="user", target_id=u.id,
          label=u.email, before=before, after=_snapshot(u), reason=body.reason)
    if body.suspend and body.notify:
        from emails import send_template
        await send_template(db, "account_suspended", u.email, {"name": u.name or u.email.split("@")[0],
                            "message": body.message or "We noticed activity that goes against our Acceptable Use Policy."}, user_id=u.id)
    await db.commit()
    return {"ok": True, "status": status_of(u)}


@router.post("/users/{uid}/password-reset")
async def force_password_reset(uid: int, request: Request, p: Principal = Depends(require_perm("users.write")),
                               db: AsyncSession = Depends(get_db)):
    """Email a one-time reset link (1 h) and sign the user out everywhere. Staff never see the link."""
    from emails import send_template
    u = await get_user(db, uid)
    _guard_staff_target(p, u)
    if not get_settings().mail_enabled:
        raise HTTPException(503, "Mail is off on this server, so the reset link can't be emailed yet. "
                                 "Use manage.py set-password, or turn mail on first.")
    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=u.id, token_hash=sha256(token), expires_at=utcnow() + timedelta(hours=1), created_by=p.user.id))
    await db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    status = await send_template(db, "password_reset", u.email, {"name": u.name or u.email.split("@")[0],
                                 "link": f"https://login.aiwazz.in/reset-password?token={token}"}, user_id=u.id)
    audit(db, request, p.user, "user.password_reset", target_type="user", target_id=u.id, label=u.email,
          after={"email": status}, full=True)
    await db.commit()
    return {"ok": True, "email": status}


@router.post("/users/{uid}/sessions/revoke")
async def revoke_sessions(uid: int, request: Request, p: Principal = Depends(require_perm("users.write")),
                          db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    _guard_staff_target(p, u)
    q = delete(UserSession).where(UserSession.user_id == u.id)
    if u.id == p.user.id:
        q = q.where(UserSession.id != p.session.id)
    n = (await db.execute(q)).rowcount or 0
    audit(db, request, p.user, "user.sessions.revoke", target_type="user", target_id=u.id, label=u.email,
          after={"sessions": n}, full=True)
    await db.commit()
    return {"ok": True, "sessions": n}


@router.delete("/users/{uid}/sessions/{sid}")
async def revoke_session(uid: int, sid: int, request: Request, p: Principal = Depends(require_perm("users.write")),
                         db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    _guard_staff_target(p, u)
    sess = await db.get(UserSession, sid)
    if sess is None or sess.user_id != uid:
        raise HTTPException(404, "Session not found")
    await db.delete(sess)
    audit(db, request, p.user, "user.session.revoke", target_type="user", target_id=u.id, label=u.email,
          after={"session": sid, "ip": sess.ip}, full=True)
    await db.commit()
    return {"ok": True}


@router.delete("/users/{uid}/keys/{kid}")
async def revoke_user_key(uid: int, kid: int, request: Request, p: Principal = Depends(require_perm("users.write")),
                          db: AsyncSession = Depends(get_db)):
    k = await db.get(ApiKey, kid)
    if k is None or k.user_id != uid or k.revoked_at:
        raise HTTPException(404, "API key not found")
    k.revoked_at = utcnow()
    audit(db, request, p.user, "user.api_key.revoke", target_type="user", target_id=uid, label=k.user.email,
          after={"key": k.prefix + "…", "name": k.name}, full=True)
    await db.commit()
    return {"ok": True}


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post("/users/{uid}/notes")
async def add_note(uid: int, body: NoteIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                   db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    n = UserNote(user_id=u.id, author_id=p.user.id, author_email=p.user.email, body=body.body.strip())
    db.add(n)
    audit(db, request, p.user, "user.note.add", target_type="user", target_id=u.id, label=u.email)
    await db.commit()
    return {"id": n.id}


@router.delete("/users/{uid}/notes/{nid}")
async def delete_note(uid: int, nid: int, request: Request, p: Principal = Depends(require_perm("users.write")),
                      db: AsyncSession = Depends(get_db)):
    n = await db.get(UserNote, nid)
    if n is None or n.user_id != uid:
        raise HTTPException(404, "Note not found")
    if n.author_id != p.user.id and p.user.role not in ("owner", "admin"):
        raise HTTPException(403, "Only the author or an admin can delete this note")
    await db.delete(n)
    audit(db, request, p.user, "user.note.delete", target_type="user", target_id=uid, before={"body": n.body[:200]}, full=True)
    await db.commit()
    return {"ok": True}


class TagsIn(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


def _clean_tags(tags: list[str]) -> list[str]:
    import re
    out = []
    for t in tags:
        t = re.sub(r"[^a-z0-9_-]+", "-", t.strip().lower()).strip("-")[:32]
        if t and t not in out:
            out.append(t)
    return out


async def _set_tags(db: AsyncSession, uid: int, tags: list[str]) -> None:
    await db.execute(delete(UserTag).where(UserTag.user_id == uid))
    for t in tags:
        db.add(UserTag(user_id=uid, tag=t))


@router.put("/users/{uid}/tags")
async def set_tags(uid: int, body: TagsIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                   db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    before = (await _tags_for(db, [uid]))[uid]
    tags = _clean_tags(body.tags)
    await _set_tags(db, uid, tags)
    audit(db, request, p.user, "user.tags", target_type="user", target_id=uid, label=u.email,
          before={"tags": before}, after={"tags": tags})
    await db.commit()
    return {"tags": tags}


class ProfileIn(BaseModel):
    name: str = Field(default="", max_length=100)


@router.put("/users/{uid}/profile")
async def set_profile(uid: int, body: ProfileIn, request: Request, p: Principal = Depends(require_perm("users.write")),
                      db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    before = _snapshot(u)
    u.name = body.name.strip()
    audit(db, request, p.user, "user.profile", target_type="user", target_id=uid, label=u.email, before=before, after=_snapshot(u))
    await db.commit()
    return {"ok": True}


# ── DPDP export ──────────────────────────────────────────────────────────────
async def export_user_data(db: AsyncSession, u: User, request: Request) -> dict:
    """Everything we hold about the user (Privacy Policy: right to access). Audio links work while the files exist."""
    gens = (await db.execute(select(Generation).where(Generation.user_id == u.id).order_by(Generation.created_at))).scalars().all()
    jm = request.app.state.jobs
    keys = (await db.execute(select(ApiKey).where(ApiKey.user_id == u.id))).scalars().all()
    prons = (await db.execute(select(Pronunciation).where(Pronunciation.user_id == u.id))).scalars().all()
    billing = await user_billing(u.id, None, db)  # type: ignore[arg-type]
    sessions = (await db.execute(select(UserSession).where(UserSession.user_id == u.id))).scalars().all()
    return {
        "exported_at": iso(utcnow()), "format": "AiWazz account export v1",
        "account": {"id": u.id, "email": u.email, "name": u.name, "created_at": iso(u.created_at), "plan": u.effective_plan,
                    "plan_until": iso(u.plan_until), "last_login_at": iso(u.last_login_at),
                    "billing_details": {"name": u.billing_name, "gstin": u.billing_gstin, "state": u.billing_state,
                                        "address": u.billing_address}},
        "consent": {"accepted_at": iso(u.consent_at), "terms_version": u.terms_version, "ip": u.consent_ip,
                    "marketing_opt_in": u.marketing_opt_in},
        "generations": [_gen_row(g) | {"text_excerpt": g.text_excerpt,
                                       "audio_mp3": f"https://login.aiwazz.in/api/audio/{g.id}?format=mp3"
                                       if jm.audio_path(g.id, "mp3") else None} for g in gens],
        "api_keys": [{"name": k.name, "prefix": k.prefix, "created_at": iso(k.created_at), "last_used_at": iso(k.last_used_at),
                      "revoked_at": iso(k.revoked_at)} for k in keys],
        "pronunciations": [{"word": x.word, "say_as": x.say_as} for x in prons],
        "sessions": [{"created_at": iso(s.created_at), "last_seen_at": iso(s.last_seen_at), "ip": s.ip, "user_agent": s.user_agent}
                     for s in sessions],
        **billing,
    }


@router.get("/users/{uid}/export")
async def export_user(uid: int, request: Request, p: Principal = Depends(require_perm("users.export")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    data = await export_user_data(db, u, request)
    audit(db, request, p.user, "user.export", target_type="user", target_id=uid, label=u.email,
          after={"generations": len(data["generations"])}, full=True)
    await db.commit()
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="aiwazz-user-{uid}-export.json"'})


# ── Delete ───────────────────────────────────────────────────────────────────
class DeleteIn(BaseModel):
    confirm_email: str = Field(max_length=254)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/users/{uid}/delete")
async def delete_user(uid: int, body: DeleteIn, request: Request, p: Principal = Depends(require_perm("users.delete")),
                      _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    from accounts import delete_user_data
    from billing.routes import cancel_for_account_deletion
    u = await get_user(db, uid)
    if u.role == "owner":
        raise HTTPException(422, "The owner account can't be deleted. Transfer ownership first.")
    if u.id == p.user.id:
        raise HTTPException(422, "Delete your own account from Settings in the app")
    _guard_staff_target(p, u)
    if body.confirm_email.strip().lower() != u.email:
        raise HTTPException(422, "Type the user's email exactly to confirm")
    await cancel_for_account_deletion(db, u.id)   # fails closed if Razorpay is unreachable
    email = u.email
    audit(db, request, p.user, "user.delete", target_type="user", target_id=uid, label=email, before=_snapshot(u),
          reason=body.reason, full=True)
    reference, n = await delete_user_data(db, u)
    await db.commit()
    return {"ok": True, "reference": reference, "deleted_generations": n}


# ── Impersonation (read-only "view as user") ─────────────────────────────────
class ImpersonateIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/users/{uid}/impersonate")
async def impersonate(uid: int, body: ImpersonateIn, request: Request, p: Principal = Depends(require_perm("users.impersonate")),
                      db: AsyncSession = Depends(get_db)):
    u = await get_user(db, uid)
    if u.is_staff:
        raise HTTPException(422, "Staff accounts can't be viewed as a user")
    if not u.is_active or u.suspended_at:
        raise HTTPException(422, "This account is disabled or suspended")
    until = utcnow() + timedelta(minutes=get_settings().impersonate_minutes)
    p.session.impersonate_user_id, p.session.impersonate_until = u.id, until
    audit(db, request, p.user, "impersonate.start", target_type="user", target_id=u.id, label=u.email,
          after={"until": iso(until)}, reason=body.reason, full=True)
    await db.commit()
    return {"ok": True, "until": iso(until), "redirect": "/generate"}


stop_router = APIRouter(prefix="/api/admin", include_in_schema=False)


@stop_router.post("/impersonate/stop", dependencies=[Depends(csrf_protect)])
async def impersonate_stop(request: Request, p: Principal | None = Depends(optional_principal), db: AsyncSession = Depends(get_db)):
    if p is None or p.session is None or not p.session.impersonate_user_id:
        return {"ok": True}
    target_id = p.session.impersonate_user_id
    staff = p.impersonator or p.user
    sess = await db.get(UserSession, p.session.id)
    sess.impersonate_user_id = sess.impersonate_until = None
    audit(db, request, staff, "impersonate.stop", target_type="user", target_id=target_id, label=p.user.email)
    await db.commit()
    return {"ok": True, "redirect": f"/admin/users/{target_id}"}


# ── Bulk ─────────────────────────────────────────────────────────────────────
class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(tag_add|tag_remove|plan|email)$")
    tag: str = Field(default="", max_length=32)
    plan: str = Field(default="", pattern="^(|free|starter|creator|pro)$")
    until: date | None = None
    reason: str = Field(default="", max_length=255)
    subject: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=5000)


@router.post("/users/bulk")
async def bulk(body: BulkIn, request: Request, p: Principal = Depends(require_perm("users.write", "users.bulk")),
               db: AsyncSession = Depends(get_db)):
    from .. import deps
    users = (await db.execute(select(User).where(User.id.in_(body.ids)))).scalars().all()
    if not users:
        raise HTTPException(404, "No matching users")
    done = 0
    if body.action in ("tag_add", "tag_remove"):
        tag = (_clean_tags([body.tag]) or [""])[0]
        if not tag:
            raise HTTPException(422, "Enter a tag")
        for u in users:
            if body.action == "tag_add":
                if not (await db.execute(select(UserTag.id).where(UserTag.user_id == u.id, UserTag.tag == tag))).first():
                    db.add(UserTag(user_id=u.id, tag=tag))
                    done += 1
            else:
                done += (await db.execute(delete(UserTag).where(UserTag.user_id == u.id, UserTag.tag == tag))).rowcount or 0
    elif body.action == "plan":
        if not deps.stepup_ok(p):
            raise HTTPException(403, "Confirm it's you (password + 2FA code) to continue", headers={"X-Step-Up": "required"})
        if not body.plan or len(body.reason) < 3:
            raise HTTPException(422, "Choose a plan and give a reason")
        for u in users:
            if u.is_staff:
                continue
            before = _snapshot(u)
            u.plan, u.plan_until = body.plan, end_of_ist_day(body.until) if body.until and body.plan != "free" else None
            audit(db, request, p.user, "user.plan.change", target_type="user", target_id=u.id, label=u.email,
                  before=before, after=_snapshot(u), reason=f"bulk: {body.reason}")
            done += 1
    else:   # email
        from emails import send_template
        if not body.subject.strip() or not body.message.strip():
            raise HTTPException(422, "Write a subject and a message")
        for u in users:
            await send_template(db, "support_reply", u.email, {"name": u.name or u.email.split("@")[0], "subject": body.subject,
                                "body": body.message, "agent": p.user.name or "The AiWazz team"}, user_id=u.id)
            done += 1
    audit(db, request, p.user, f"user.bulk.{body.action}", target_type="users", label=f"{len(users)} users",
          after={"ids": [u.id for u in users][:100], "tag": body.tag, "plan": body.plan, "subject": body.subject}, full=True,
          reason=body.reason)
    await db.commit()
    return {"ok": True, "affected": done, "mail_enabled": get_settings().mail_enabled}

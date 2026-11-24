"""A4: support inbox (tickets from contact form, invite requests, grievances, misuse reports; status, assignee,
priority, internal notes, email replies threaded by Message-ID, canned replies) and moderation (flags queue with
actions, rule editor with a tester, blocklist)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from db import get_db, utcnow
from models import (STAFF_ROLES, BlockEntry, CannedReply, Flag, Generation, ModerationRule, Ticket, TicketMessage, User,
                    UserSession)
from settings import get_settings

from .. import moderation, support
from ..audit import audit
from ..deps import require_perm, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)


# ── Tickets ──────────────────────────────────────────────────────────────────
def _overdue(t: Ticket) -> str | None:
    now = utcnow()
    if t.status == "resolved":
        return None
    if t.ack_due_at and not t.acknowledged_at and now > t.ack_due_at:
        return "acknowledgement"
    if t.resolve_due_at and now > t.resolve_due_at:
        return "resolution"
    return None


def _ticket_row(t: Ticket, assignee: str = "", last: str = "") -> dict:
    return {"id": t.id, "reference": t.reference, "kind": t.kind, "status": t.status, "priority": t.priority,
            "assignee_id": t.assignee_id, "assignee": assignee, "subject": t.subject, "name": t.name, "email": t.email,
            "user_id": t.user_id, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at), "preview": last[:160],
            "acknowledged_at": iso(t.acknowledged_at), "resolved_at": iso(t.resolved_at), "ack_due_at": iso(t.ack_due_at),
            "resolve_due_at": iso(t.resolve_due_at), "overdue": _overdue(t)}


@router.get("/tickets")
async def list_tickets(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                       kind: str = Query("", max_length=16), priority: str = Query("", max_length=8),
                       assignee: str = Query("", max_length=8), p: Principal = Depends(require_perm("support.read")),
                       db: AsyncSession = Depends(get_db)):
    stmt = select(Ticket, User.email).outerjoin(User, User.id == Ticket.assignee_id)
    if status == "open_all":
        stmt = stmt.where(Ticket.status != "resolved")
    elif status:
        stmt = stmt.where(Ticket.status == status)
    if kind:
        stmt = stmt.where(Ticket.kind == kind)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if assignee == "me":
        stmt = stmt.where(Ticket.assignee_id == p.user.id)
    elif assignee == "none":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    if lp.q:
        q = lp.q.strip()
        stmt = stmt.where(or_(Ticket.subject.contains(q), Ticket.email.contains(q.lower()), Ticket.reference.contains(q.upper()),
                              Ticket.name.contains(q)))
    if status == "overdue":
        now = utcnow()
        stmt = select(Ticket, User.email).outerjoin(User, User.id == Ticket.assignee_id).where(
            Ticket.status != "resolved", or_(and_(Ticket.ack_due_at < now, Ticket.acknowledged_at.is_(None)), Ticket.resolve_due_at < now))
    page = await respond(db, request, p, stmt, lp, scalars=False, name="tickets",
                         sorts={"updated_at": Ticket.updated_at, "created_at": Ticket.created_at, "priority": Ticket.priority},
                         default_sort=Ticket.updated_at.desc(), row=lambda r: _ticket_row(r[0], r[1] or ""))
    if isinstance(page, dict) and page["items"]:
        ids = [i["id"] for i in page["items"]]
        sub = select(TicketMessage.ticket_id, func.max(TicketMessage.id).label("mid")).where(
            TicketMessage.ticket_id.in_(ids), TicketMessage.direction != "note").group_by(TicketMessage.ticket_id).subquery()
        last = dict((await db.execute(select(TicketMessage.ticket_id, TicketMessage.body).join(sub, TicketMessage.id == sub.c.mid))).all())
        for i in page["items"]:
            i["preview"] = (last.get(i["id"]) or "")[:160]
    return page


@router.get("/tickets/counts")
async def ticket_counts(p: Principal = Depends(require_perm("support.read")), db: AsyncSession = Depends(get_db)):
    rows = dict((await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))).all())
    now = utcnow()
    overdue = (await db.execute(select(func.count()).select_from(Ticket).where(
        Ticket.status != "resolved", or_(and_(Ticket.ack_due_at < now, Ticket.acknowledged_at.is_(None)), Ticket.resolve_due_at < now)))).scalar_one()
    mine = (await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status != "resolved", Ticket.assignee_id == p.user.id))).scalar_one()
    return {"by_status": rows, "overdue": overdue, "mine": mine}


async def _get_ticket(db, tid) -> Ticket:
    t = await db.get(Ticket, tid)
    if t is None:
        raise HTTPException(404, "Ticket not found")
    return t


@router.get("/tickets/{tid}")
async def ticket_detail(tid: int, p: Principal = Depends(require_perm("support.read")), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, tid)
    msgs = (await db.execute(select(TicketMessage).where(TicketMessage.ticket_id == tid).order_by(TicketMessage.id))).scalars().all()
    staff = (await db.execute(select(User.id, User.email).where(User.role.in_(STAFF_ROLES), User.is_active.is_(True)))).all()
    user = await db.get(User, t.user_id) if t.user_id else None
    assignee = next((e for i, e in staff if i == t.assignee_id), "")
    return {"ticket": _ticket_row(t, assignee) | {"thread_message_id": t.thread_message_id},
            "messages": [{"id": m.id, "direction": m.direction, "author_email": m.author_email, "body": m.body,
                          "email_status": m.email_status, "created_at": iso(m.created_at)} for m in msgs],
            "user": {"id": user.id, "email": user.email, "plan": user.effective_plan, "status": "suspended" if user.suspended_at else "active"} if user else None,
            "staff": [{"id": i, "email": e} for i, e in staff], "mail_enabled": get_settings().mail_enabled}


class TicketUpdateIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|open|waiting|resolved)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    assignee_id: int | None = None
    unassign: bool = False
    acknowledged: bool | None = None


@router.patch("/tickets/{tid}")
async def update_ticket(tid: int, body: TicketUpdateIn, request: Request, p: Principal = Depends(require_perm("support.write")),
                        db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, tid)
    before = {"status": t.status, "priority": t.priority, "assignee_id": t.assignee_id, "acknowledged": bool(t.acknowledged_at)}
    if body.status:
        t.status = body.status
        t.resolved_at = utcnow() if body.status == "resolved" else None
    if body.priority:
        t.priority = body.priority
    if body.unassign:
        t.assignee_id = None
    elif body.assignee_id is not None:
        a = await db.get(User, body.assignee_id)
        if a is None or not a.is_staff:
            raise HTTPException(422, "Assign to a staff member")
        t.assignee_id = a.id
    if body.acknowledged and not t.acknowledged_at:
        t.acknowledged_at = utcnow()           # e.g. acknowledged by phone / from the mailbox
    t.updated_at = utcnow()
    after = {"status": t.status, "priority": t.priority, "assignee_id": t.assignee_id, "acknowledged": bool(t.acknowledged_at)}
    audit(db, request, p.user, "support.ticket.update", target_type="ticket", target_id=t.id, label=t.reference, before=before, after=after)
    await db.commit()
    return _ticket_row(t)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    note: bool = False                      # internal note: never emailed
    status: str | None = Field(default=None, pattern="^(open|waiting|resolved)$")


@router.post("/tickets/{tid}/reply")
async def reply_ticket(tid: int, body: ReplyIn, request: Request, p: Principal = Depends(require_perm("support.write")),
                       db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, tid)
    if body.note:
        db.add(TicketMessage(ticket_id=t.id, direction="note", author_id=p.user.id, author_email=p.user.email, body=body.body))
        email_status = "note"
    else:
        m = await support.send_reply(db, t, body.body, p.user)
        email_status = m.email_status
    t.status = body.status or ("waiting" if not body.note else t.status if t.status != "new" else "open")
    if t.status == "resolved":
        t.resolved_at = utcnow()
    t.updated_at = utcnow()
    audit(db, request, p.user, "support.ticket.note" if body.note else "support.ticket.reply", target_type="ticket",
          target_id=t.id, label=t.reference, after={"email": email_status, "status": t.status}, full=True)
    await db.commit()
    return {"ok": True, "email_status": email_status, "ticket": _ticket_row(t)}


class CannedIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)


@router.get("/canned-replies")
async def list_canned(p: Principal = Depends(require_perm("support.read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CannedReply).order_by(CannedReply.title))).scalars().all()
    return {"items": [{"id": c.id, "title": c.title, "body": c.body} for c in rows]}


@router.post("/canned-replies")
async def create_canned(body: CannedIn, request: Request, p: Principal = Depends(require_perm("support.write")),
                        db: AsyncSession = Depends(get_db)):
    c = CannedReply(title=body.title.strip(), body=body.body.strip(), created_by=p.user.id)
    db.add(c)
    await db.flush()
    audit(db, request, p.user, "support.canned.create", target_type="canned_reply", target_id=c.id, label=c.title)
    await db.commit()
    return {"id": c.id, "title": c.title, "body": c.body}


@router.put("/canned-replies/{cid}")
async def update_canned(cid: int, body: CannedIn, request: Request, p: Principal = Depends(require_perm("support.write")),
                        db: AsyncSession = Depends(get_db)):
    c = await db.get(CannedReply, cid)
    if c is None:
        raise HTTPException(404, "Not found")
    c.title, c.body = body.title.strip(), body.body.strip()
    audit(db, request, p.user, "support.canned.update", target_type="canned_reply", target_id=c.id, label=c.title)
    await db.commit()
    return {"id": c.id, "title": c.title, "body": c.body}


@router.delete("/canned-replies/{cid}")
async def delete_canned(cid: int, request: Request, p: Principal = Depends(require_perm("support.write")),
                        db: AsyncSession = Depends(get_db)):
    c = await db.get(CannedReply, cid)
    if c is None:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    audit(db, request, p.user, "support.canned.delete", target_type="canned_reply", target_id=cid, label=c.title)
    await db.commit()
    return {"ok": True}


# ── Moderation: flags ────────────────────────────────────────────────────────
def _flag_row(f: Flag, email: str = "") -> dict:
    return {"id": f.id, "source": f.source, "user_id": f.user_id, "email": email, "generation_id": f.generation_id,
            "rule_id": f.rule_id, "rule_name": f.rule_name, "category": f.category, "severity": f.severity, "matched": f.matched,
            "detail": f.detail, "blocked": f.blocked, "status": f.status, "action": f.action, "note": f.note,
            "ticket_id": f.ticket_id, "reviewed_at": iso(f.reviewed_at), "created_at": iso(f.created_at)}


@router.get("/flags")
async def list_flags(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16),
                     source: str = Query("", max_length=16), severity: str = Query("", max_length=8),
                     p: Principal = Depends(require_perm("moderation.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(Flag, User.email).outerjoin(User, User.id == Flag.user_id)
    if status:
        stmt = stmt.where(Flag.status == status)
    if source:
        stmt = stmt.where(Flag.source == source)
    if severity:
        stmt = stmt.where(Flag.severity == severity)
    if lp.q:
        stmt = stmt.where(or_(User.email.contains(lp.q.lower()), Flag.rule_name.contains(lp.q), Flag.matched.contains(lp.q)))
    return await respond(db, request, p, stmt, lp, scalars=False, name="flags", sorts={"created_at": Flag.created_at},
                         default_sort=Flag.id.desc(), row=lambda r: _flag_row(r[0], r[1] or ""))


class FlagActionIn(BaseModel):
    action: str = Field(pattern="^(dismiss|warn|suspend|delete_audio|report_note)$")
    note: str = Field(default="", max_length=500)
    message: str = Field(default="", max_length=2000)     # warn: text of the email


@router.post("/flags/{fid}/action")
async def flag_action(fid: int, body: FlagActionIn, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                      db: AsyncSession = Depends(get_db)):
    from emails import send_template
    f = await db.get(Flag, fid)
    if f is None:
        raise HTTPException(404, "Flag not found")
    user = await db.get(User, f.user_id) if f.user_id else None
    result = ""
    if body.action == "dismiss":
        f.status, f.action = "dismissed", ""
    elif body.action == "warn":
        if user is None:
            raise HTTPException(422, "No account to warn")
        result = await send_template(db, "support_reply", user.email, {
            "name": user.name or user.email.split("@")[0], "subject": "About your recent voiceover",
            "body": body.message or "One of your recent scripts looks like it goes against our Acceptable Use Policy "
                                    "(aiwazz.in/acceptable-use/). Please make sure your voiceovers follow it; repeated misuse "
                                    "can lead to the account being paused.", "agent": "AiWazz Trust & Safety"}, user_id=user.id)
        f.status, f.action = "actioned", "warned"
    elif body.action == "suspend":
        if user is None:
            raise HTTPException(422, "No account to suspend")
        if user.is_staff:
            raise HTTPException(403, "Staff accounts are managed in Team & roles")
        user.suspended_at, user.suspend_reason = utcnow(), f"Moderation flag #{f.id}: {body.note or f.rule_name}"[:255]
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        f.status, f.action = "actioned", "suspended"
    elif body.action == "delete_audio":
        if not f.generation_id:
            raise HTTPException(422, "This flag has no generation")
        audio = get_settings().audio_dir
        for ext in ("mp3", "wav", "json"):
            (audio / f"{f.generation_id}.{ext}").unlink(missing_ok=True)
        gen = await db.get(Generation, f.generation_id)
        if gen:
            gen.status, gen.error = "error", "Removed by moderation"
        f.status, f.action = "actioned", "audio_deleted"
    else:
        f.status, f.action = "actioned", "reported"
    f.note = (body.note or f.note)[:500]
    f.reviewed_by, f.reviewed_at = p.user.id, utcnow()
    audit(db, request, p.user, f"moderation.flag.{body.action}", target_type="flag", target_id=f.id,
          label=user.email if user else f.rule_name, after={"status": f.status, "action": f.action, "email": result},
          reason=body.note, full=True)
    await db.commit()
    return _flag_row(f, user.email if user else "")


# ── Moderation: rules ────────────────────────────────────────────────────────
def _rule_row(r: ModerationRule) -> dict:
    return {"id": r.id, "name": r.name, "category": r.category, "kind": r.kind, "pattern": r.pattern, "severity": r.severity,
            "action": r.action, "active": r.active, "updated_at": iso(r.updated_at)}


class RuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(pattern="^(impersonation|scam|threat|explicit|other)$")
    kind: str = Field(pattern="^(keywords|regex)$")
    pattern: str = Field(min_length=1, max_length=5000)
    severity: str = Field(pattern="^(low|medium|high)$")
    action: str = Field(pattern="^(flag|block)$")
    active: bool = True


@router.get("/moderation/rules")
async def list_rules(p: Principal = Depends(require_perm("moderation.read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ModerationRule).order_by(ModerationRule.id))).scalars().all()
    counts = dict((await db.execute(select(Flag.rule_id, func.count()).where(Flag.created_at >= utcnow() - timedelta(days=30))
                                    .group_by(Flag.rule_id))).all())
    return {"items": [_rule_row(r) | {"hits_30d": counts.get(r.id, 0)} for r in rows]}


def _check_rule(body: RuleIn) -> None:
    if moderation.compile_rule(ModerationRule(kind=body.kind, pattern=body.pattern)) is None:
        raise HTTPException(422, "The pattern isn't valid")


@router.post("/moderation/rules")
async def create_rule(body: RuleIn, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                      db: AsyncSession = Depends(get_db)):
    _check_rule(body)
    r = ModerationRule(**body.model_dump(), created_by=p.user.id)
    db.add(r)
    await db.flush()
    audit(db, request, p.user, "moderation.rule.create", target_type="rule", target_id=r.id, label=r.name, after=_rule_row(r), full=True)
    await db.commit()
    moderation.clear_cache()
    return _rule_row(r)


@router.put("/moderation/rules/{rid}")
async def update_rule(rid: int, body: RuleIn, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                      db: AsyncSession = Depends(get_db)):
    r = await db.get(ModerationRule, rid)
    if r is None:
        raise HTTPException(404, "Rule not found")
    _check_rule(body)
    before = _rule_row(r)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    r.updated_at = utcnow()
    audit(db, request, p.user, "moderation.rule.update", target_type="rule", target_id=r.id, label=r.name, before=before, after=_rule_row(r))
    await db.commit()
    moderation.clear_cache()
    return _rule_row(r)


@router.delete("/moderation/rules/{rid}")
async def delete_rule(rid: int, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                      db: AsyncSession = Depends(get_db)):
    r = await db.get(ModerationRule, rid)
    if r is None:
        raise HTTPException(404, "Rule not found")
    audit(db, request, p.user, "moderation.rule.delete", target_type="rule", target_id=r.id, label=r.name, before=_rule_row(r), full=True)
    await db.delete(r)
    await db.commit()
    moderation.clear_cache()
    return {"ok": True}


class RuleTestIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    kind: str | None = Field(default=None, pattern="^(keywords|regex)$")
    pattern: str | None = Field(default=None, max_length=5000)


@router.post("/moderation/test")
async def test_rules(body: RuleTestIn, p: Principal = Depends(require_perm("moderation.read")), db: AsyncSession = Depends(get_db)):
    """Try a text against one draft pattern, or against all active rules. Nothing is stored."""
    if body.pattern:
        pat = moderation.compile_rule(ModerationRule(kind=body.kind or "keywords", pattern=body.pattern))
        if pat is None:
            raise HTTPException(422, "The pattern isn't valid")
        return {"matches": [{"rule": "draft", "term": m.group(0)} for m in pat.finditer(body.text)][:20]}
    return {"matches": [{"rule": m.rule.name, "term": m.term, "action": m.rule.action, "severity": m.rule.severity}
                        for m in await moderation.screen(db, body.text)]}


# ── Blocklist ────────────────────────────────────────────────────────────────
class BlockIn(BaseModel):
    kind: str = Field(pattern="^(email|domain|ip)$")
    value: str = Field(min_length=3, max_length=254)
    reason: str = Field(default="", max_length=255)


@router.get("/moderation/blocklist")
async def list_blocklist(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("moderation.read")),
                         db: AsyncSession = Depends(get_db)):
    stmt = select(BlockEntry)
    if lp.q:
        stmt = stmt.where(BlockEntry.value.contains(lp.q.lower()))
    return await respond(db, request, p, stmt, lp, sorts={"created_at": BlockEntry.created_at}, default_sort=BlockEntry.id.desc(),
                         name="blocklist", row=lambda b: {"id": b.id, "kind": b.kind, "value": b.value, "reason": b.reason,
                                                          "created_at": iso(b.created_at)})


@router.post("/moderation/blocklist")
async def add_block(body: BlockIn, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                    db: AsyncSession = Depends(get_db)):
    import ipaddress
    value = body.value.strip().lower()
    if body.kind == "ip":
        try:
            value = str(ipaddress.ip_network(value, strict=False))
        except ValueError as e:
            raise HTTPException(422, "Not an IP address or range") from e
    elif body.kind == "email" and "@" not in value:
        raise HTTPException(422, "Not an email address")
    elif body.kind == "domain":
        value = value.lstrip("@")
        if "." not in value or "@" in value:
            raise HTTPException(422, "Enter a domain like example.com")
    if (await db.execute(select(BlockEntry.id).where(BlockEntry.kind == body.kind, BlockEntry.value == value))).first():
        raise HTTPException(409, "Already blocked")
    b = BlockEntry(kind=body.kind, value=value, reason=body.reason.strip(), created_by=p.user.id)
    db.add(b)
    await db.flush()
    audit(db, request, p.user, "moderation.block.add", target_type="blocklist", target_id=b.id, label=f"{b.kind}:{b.value}", reason=b.reason)
    await db.commit()
    return {"id": b.id, "kind": b.kind, "value": b.value}


@router.delete("/moderation/blocklist/{bid}")
async def remove_block(bid: int, request: Request, p: Principal = Depends(require_perm("moderation.write")),
                       db: AsyncSession = Depends(get_db)):
    b = await db.get(BlockEntry, bid)
    if b is None:
        raise HTTPException(404, "Not found")
    audit(db, request, p.user, "moderation.block.remove", target_type="blocklist", target_id=b.id, label=f"{b.kind}:{b.value}")
    await db.delete(b)
    await db.commit()
    return {"ok": True}

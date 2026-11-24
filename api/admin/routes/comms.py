"""A7: email templates (edit, live preview, test send), sending log, suppression list; announcements (in-app
banners) and the public changelog (aiwazz.in/changelog/, landing rebuild on publish)."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import emails
from auth.deps import Principal, csrf_protect
from db import get_db, utcnow
from models import Announcement, ChangelogEntry, EmailLog, EmailSuppression, EmailTemplate
from settings import get_settings

from .. import jobs, legal_store
from ..audit import audit
from ..deps import require_perm, staff_principal
from ..listing import ListParams, iso, respond

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)
IST = timedelta(hours=5, minutes=30)
SAMPLE = {"name": "Riya", "app_url": "https://login.aiwazz.in/generate", "code": "ABCD-EFGH", "signup_url": "https://login.aiwazz.in/signup?invite=ABCD-EFGH",
          "plan_note": "Your account starts on the Creator plan until 24 Feb 2027, free.\n\n", "expires": "08 Dec 2026",
          "link": "https://login.aiwazz.in/reset-password?token=example", "amount": "₹588.82", "plan": "Creator",
          "invoice_number": "AWZ/2026-27/00001", "grace_until": "01 Dec 2026", "until_note": " until 24 Feb 2027",
          "until": "24 Dec 2026", "reference": "AWZ-T-000123", "message": "We noticed scripts that go against our Acceptable Use Policy.",
          "subject": "Question about my invoice", "body": "Thanks for writing! Here's the answer…", "agent": "Ankit",
          "received": "24 Nov 2026", "due": "09 Dec 2026", "summary": "Disk 90% full", "lines": "PROBLEM: Disk 90% full (3.1 GB free)"}


# ── Email templates ──────────────────────────────────────────────────────────
@router.get("/email/templates")
async def list_templates(p: Principal = Depends(require_perm("email.read")), db: AsyncSession = Depends(get_db)):
    over = {t.key: t for t in (await db.execute(select(EmailTemplate))).scalars()}
    return {"items": [{"key": k, "name": t.name, "variables": list(t.variables), "customized": k in over,
                       "subject": over[k].subject if k in over else t.subject, "body": over[k].body if k in over else t.body,
                       "default_subject": t.subject, "default_body": t.body, "updated_at": iso(over[k].updated_at) if k in over else None}
                      for k, t in emails.DEFAULTS.items()], "mail_enabled": get_settings().mail_enabled}


class TemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


def _check_vars(key: str, body: TemplateIn) -> None:
    import re
    allowed = set(emails.DEFAULTS[key].variables)
    used = set(re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", body.subject + body.body))
    if unknown := used - allowed:
        raise HTTPException(422, f"Unknown variable(s): {', '.join(sorted(unknown))}. Allowed: {', '.join(sorted(allowed))}")


@router.put("/email/templates/{key}")
async def save_template(key: str, body: TemplateIn, request: Request, p: Principal = Depends(require_perm("email.write")),
                        db: AsyncSession = Depends(get_db)):
    if key not in emails.DEFAULTS:
        raise HTTPException(404, "Unknown template")
    _check_vars(key, body)
    row = await db.get(EmailTemplate, key)
    before = {"subject": row.subject, "body": row.body} if row else {"subject": emails.DEFAULTS[key].subject, "body": emails.DEFAULTS[key].body}
    if row is None:
        row = EmailTemplate(key=key, subject=body.subject, body=body.body, updated_by=p.user.id)
        db.add(row)
    row.subject, row.body, row.updated_by = body.subject, body.body, p.user.id
    audit(db, request, p.user, "email.template.save", target_type="email_template", target_id=key, label=key, before=before,
          after={"subject": body.subject, "body": body.body})
    await db.commit()
    return {"ok": True}


@router.delete("/email/templates/{key}")
async def reset_template(key: str, request: Request, p: Principal = Depends(require_perm("email.write")), db: AsyncSession = Depends(get_db)):
    row = await db.get(EmailTemplate, key)
    if row is not None:
        await db.delete(row)
        audit(db, request, p.user, "email.template.reset", target_type="email_template", target_id=key, label=key)
        await db.commit()
    return {"ok": True}


class PreviewIn(TemplateIn):
    key: str = Field(max_length=32)


@router.post("/email/preview")
async def preview(body: PreviewIn, p: Principal = Depends(require_perm("email.read"))):
    if body.key not in emails.DEFAULTS:
        raise HTTPException(404, "Unknown template")
    text = emails.fill(body.body, SAMPLE)
    return {"subject": emails.fill(body.subject, SAMPLE), "text": text, "html": emails.layout_html(text)}


class TestSendIn(BaseModel):
    key: str = Field(max_length=32)


@router.post("/email/test-send")
async def test_send(body: TestSendIn, request: Request, p: Principal = Depends(require_perm("email.write")), db: AsyncSession = Depends(get_db)):
    """Send the saved template with sample values to YOUR address (logged like any other email)."""
    if body.key not in emails.DEFAULTS:
        raise HTTPException(404, "Unknown template")
    status = await emails.send_template(db, body.key, p.user.email, SAMPLE, user_id=p.user.id)
    audit(db, request, p.user, "email.test_send", target_type="email_template", target_id=body.key, after={"status": status}, full=True)
    await db.commit()
    return {"status": status, "to": p.user.email}


@router.get("/email/log")
async def email_log(request: Request, lp: ListParams = Depends(), status: str = Query("", max_length=16), template: str = Query("", max_length=32),
                    p: Principal = Depends(require_perm("email.read")), db: AsyncSession = Depends(get_db)):
    stmt = select(EmailLog)
    if status:
        stmt = stmt.where(EmailLog.status == status)
    if template:
        stmt = stmt.where(EmailLog.template == template)
    if lp.q:
        stmt = stmt.where(or_(EmailLog.to_email.contains(lp.q.lower()), EmailLog.subject.contains(lp.q), EmailLog.message_id.contains(lp.q)))
    return await respond(db, request, p, stmt, lp, sorts={"created_at": EmailLog.created_at}, default_sort=EmailLog.id.desc(), name="email-log",
                         row=lambda e: {"id": e.id, "to": e.to_email, "template": e.template, "subject": e.subject, "status": e.status,
                                        "message_id": e.message_id, "error": e.error, "user_id": e.user_id, "created_at": iso(e.created_at)})


class SuppressIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    reason: str = Field("manual", pattern="^(hard_bounce|unsubscribe|manual)$")
    note: str = Field("", max_length=255)


@router.get("/email/suppressions")
async def suppressions(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("email.read")),
                       db: AsyncSession = Depends(get_db)):
    stmt = select(EmailSuppression)
    if lp.q:
        stmt = stmt.where(EmailSuppression.email.contains(lp.q.lower()))
    return await respond(db, request, p, stmt, lp, sorts={"created_at": EmailSuppression.created_at}, default_sort=EmailSuppression.created_at.desc(),
                         name="suppressions", row=lambda s: {"id": s.email, "email": s.email, "reason": s.reason, "note": s.note, "created_at": iso(s.created_at)})


@router.post("/email/suppressions")
async def add_suppression(body: SuppressIn, request: Request, p: Principal = Depends(require_perm("email.write")), db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Not an email address")
    if await db.get(EmailSuppression, email):
        raise HTTPException(409, "Already suppressed")
    db.add(EmailSuppression(email=email, reason=body.reason, note=body.note))
    audit(db, request, p.user, "email.suppress.add", target_type="email", target_id=email, label=email, reason=body.reason)
    await db.commit()
    return {"ok": True}


@router.delete("/email/suppressions/{email}")
async def remove_suppression(email: str, request: Request, p: Principal = Depends(require_perm("email.write")), db: AsyncSession = Depends(get_db)):
    row = await db.get(EmailSuppression, email.lower())
    if row is None:
        raise HTTPException(404, "Not found")
    await db.delete(row)
    audit(db, request, p.user, "email.suppress.remove", target_type="email", target_id=row.email, label=row.email)
    await db.commit()
    return {"ok": True}


# ── Announcements ────────────────────────────────────────────────────────────
def _ann(a: Announcement) -> dict:
    now = utcnow()
    state = "off" if not a.active else "scheduled" if a.starts_at and a.starts_at > now else "ended" if a.ends_at and a.ends_at <= now else "live"
    return {"id": a.id, "text": a.text, "level": a.level, "audience": a.audience, "starts_at": iso(a.starts_at), "ends_at": iso(a.ends_at),
            "dismissible": a.dismissible, "active": a.active, "state": state, "created_at": iso(a.created_at)}


class AnnouncementIn(BaseModel):
    text: str = Field(min_length=3, max_length=300)
    level: str = Field("info", pattern="^(info|warning)$")
    audience: str = Field("all", pattern="^(all|free|paid|admins|plan:(starter|creator|pro))$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    dismissible: bool = True
    active: bool = True


def _naive(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d.astimezone(__import__("datetime").UTC).replace(tzinfo=None) if d.tzinfo else d


@router.get("/announcements")
async def list_announcements(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("announcements.read")),
                             db: AsyncSession = Depends(get_db)):
    return await respond(db, request, p, select(Announcement), lp, sorts={"created_at": Announcement.created_at},
                         default_sort=Announcement.id.desc(), row=_ann, name="announcements")


@router.post("/announcements")
async def create_announcement(body: AnnouncementIn, request: Request, p: Principal = Depends(require_perm("announcements.write")),
                              db: AsyncSession = Depends(get_db)):
    a = Announcement(**(body.model_dump() | {"starts_at": _naive(body.starts_at), "ends_at": _naive(body.ends_at)}), created_by=p.user.id)
    db.add(a)
    await db.flush()
    audit(db, request, p.user, "announcement.create", target_type="announcement", target_id=a.id, label=a.text[:80], after=_ann(a), full=True)
    await db.commit()
    return _ann(a)


@router.put("/announcements/{aid}")
async def update_announcement(aid: int, body: AnnouncementIn, request: Request, p: Principal = Depends(require_perm("announcements.write")),
                              db: AsyncSession = Depends(get_db)):
    a = await db.get(Announcement, aid)
    if a is None:
        raise HTTPException(404, "Not found")
    before = _ann(a)
    for k, v in (body.model_dump() | {"starts_at": _naive(body.starts_at), "ends_at": _naive(body.ends_at)}).items():
        setattr(a, k, v)
    audit(db, request, p.user, "announcement.update", target_type="announcement", target_id=a.id, label=a.text[:80], before=before, after=_ann(a))
    await db.commit()
    return _ann(a)


@router.delete("/announcements/{aid}")
async def delete_announcement(aid: int, request: Request, p: Principal = Depends(require_perm("announcements.write")), db: AsyncSession = Depends(get_db)):
    a = await db.get(Announcement, aid)
    if a is None:
        raise HTTPException(404, "Not found")
    audit(db, request, p.user, "announcement.delete", target_type="announcement", target_id=a.id, label=a.text[:80], before=_ann(a), full=True)
    await db.delete(a)
    await db.commit()
    return {"ok": True}


# ── Changelog ────────────────────────────────────────────────────────────────
def _cl(e: ChangelogEntry) -> dict:
    return {"id": e.id, "title": e.title, "body_md": e.body_md, "tag": e.tag, "is_published": e.is_published,
            "published_on": (e.published_on + IST).date().isoformat(), "updated_at": iso(e.updated_at)}


class ChangelogIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    body_md: str = Field(min_length=1, max_length=20000)
    published_on: date
    tag: str = Field("improved", pattern="^(new|improved|fixed)$")
    is_published: bool = False


@router.get("/changelog")
async def list_changelog(request: Request, lp: ListParams = Depends(), p: Principal = Depends(require_perm("announcements.read")),
                         db: AsyncSession = Depends(get_db)):
    page = await respond(db, request, p, select(ChangelogEntry), lp, sorts={"published_on": ChangelogEntry.published_on},
                         default_sort=ChangelogEntry.published_on.desc(), row=_cl, name="changelog")
    if isinstance(page, dict):
        page["landing_job_running"] = jobs.is_running("landing-deploy")
    return page


def _rebuild(request: Request) -> str:
    async def job():
        return await legal_store.push_and_rebuild_landing()
    return "started" if jobs.start(request.app.state.sessionmaker, "landing-deploy", job) else "already running"


@router.post("/changelog")
async def create_changelog(body: ChangelogIn, request: Request, p: Principal = Depends(require_perm("announcements.write")),
                           db: AsyncSession = Depends(get_db)):
    e = ChangelogEntry(title=body.title.strip(), body_md=body.body_md, tag=body.tag, is_published=body.is_published,
                       published_on=datetime.combine(body.published_on, datetime.min.time()) - IST, created_by=p.user.id)
    db.add(e)
    await db.flush()
    audit(db, request, p.user, "changelog.create", target_type="changelog", target_id=e.id, label=e.title, after=_cl(e), full=True)
    await db.commit()
    return _cl(e) | ({"landing_rebuild": _rebuild(request)} if e.is_published else {})


@router.put("/changelog/{cid}")
async def update_changelog(cid: int, body: ChangelogIn, request: Request, p: Principal = Depends(require_perm("announcements.write")),
                           db: AsyncSession = Depends(get_db)):
    e = await db.get(ChangelogEntry, cid)
    if e is None:
        raise HTTPException(404, "Not found")
    before = _cl(e)
    e.title, e.body_md, e.tag, e.is_published = body.title.strip(), body.body_md, body.tag, body.is_published
    e.published_on = datetime.combine(body.published_on, datetime.min.time()) - IST
    audit(db, request, p.user, "changelog.update", target_type="changelog", target_id=e.id, label=e.title, before=before, after=_cl(e))
    await db.commit()
    rebuild = before["is_published"] or e.is_published
    return _cl(e) | ({"landing_rebuild": _rebuild(request)} if rebuild else {})


@router.delete("/changelog/{cid}")
async def delete_changelog(cid: int, request: Request, p: Principal = Depends(require_perm("announcements.write")), db: AsyncSession = Depends(get_db)):
    e = await db.get(ChangelogEntry, cid)
    if e is None:
        raise HTTPException(404, "Not found")
    was = e.is_published
    audit(db, request, p.user, "changelog.delete", target_type="changelog", target_id=e.id, label=e.title, before=_cl(e), full=True)
    await db.delete(e)
    await db.commit()
    return {"ok": True} | ({"landing_rebuild": _rebuild(request)} if was else {})

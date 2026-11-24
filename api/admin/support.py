"""Support tickets: created from the contact form, invite requests and misuse reports; replies by email from
support@aiwazz.in, threaded with Message-ID / In-Reply-To / References."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import Ticket, TicketMessage, User

GRIEVANCE_ACK = timedelta(hours=24)
GRIEVANCE_RESOLVE = timedelta(days=15)


async def create_ticket(db: AsyncSession, kind: str, email: str, name: str, subject: str, body: str,
                        source_id: int | None = None, priority: str = "normal") -> Ticket:
    email = email.lower().strip()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    now = utcnow()
    t = Ticket(kind=kind, status="new", priority=priority, subject=subject[:200], name=name[:100], email=email,
               user_id=user.id if user else None, source_id=source_id, reference="pending", created_at=now, updated_at=now)
    if kind == "grievance":
        t.ack_due_at, t.resolve_due_at, t.priority = now + GRIEVANCE_ACK, now + GRIEVANCE_RESOLVE, "high"
    db.add(t)
    await db.flush()
    t.reference = f"AWZ-T-{t.id:06d}"
    db.add(TicketMessage(ticket_id=t.id, direction="in", author_email=email, body=body[:20000], created_at=now))
    return t


async def add_incoming(db: AsyncSession, t: Ticket, body: str) -> None:
    db.add(TicketMessage(ticket_id=t.id, direction="in", author_email=t.email, body=body[:20000]))
    t.updated_at = utcnow()
    if t.status in ("resolved", "waiting"):
        t.status = "open"


async def send_reply(db: AsyncSession, t: Ticket, body: str, staff: User, template: str = "support_reply") -> TicketMessage:
    """Email a reply (threaded) and store it. Returns the stored message (email_status tells what happened)."""
    from email.utils import make_msgid

    from emails import send_template
    msg_id = make_msgid(domain="aiwazz.in")
    headers = {}
    if t.thread_message_id:
        headers = {"In-Reply-To": t.thread_message_id, "References": t.thread_message_id}
    status = await send_template(db, template, t.email, {
        "name": t.name or t.email.split("@")[0], "subject": f"{t.subject} [{t.reference}]", "body": body,
        "agent": staff.name or "AiWazz support", "reference": t.reference,
        "received": f"{t.created_at + timedelta(hours=5, minutes=30):%d %b %Y}",
        "due": f"{(t.resolve_due_at or t.created_at + GRIEVANCE_RESOLVE) + timedelta(hours=5, minutes=30):%d %b %Y}"},
        user_id=t.user_id, headers=headers | {"Message-ID": msg_id})
    m = TicketMessage(ticket_id=t.id, direction="out", author_id=staff.id, author_email=staff.email, body=body,
                      message_id=msg_id, email_status=status)
    db.add(m)
    if not t.thread_message_id:
        t.thread_message_id = msg_id
    now = utcnow()
    t.updated_at = now
    if status == "sent" and t.acknowledged_at is None:
        t.acknowledged_at = now
    return m

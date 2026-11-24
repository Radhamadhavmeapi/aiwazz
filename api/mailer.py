"""Outgoing mail through the local Postfix (127.0.0.1:587, STARTTLS, user noreply@aiwazz.in).

Disabled (no-op, logged) until AIWAZZ_MAIL_ENABLED=true, which is set only after the deliverability test passes
(content/MAIL-SERVER.md). Sending never blocks or fails a request: it runs in a thread in the background.
"""
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from fastapi import Request

from settings import get_settings

log = logging.getLogger("aiwazz.mail")
_tasks: set[asyncio.Task] = set()


def build(to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None) -> EmailMessage:
    s = get_settings()
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = s.mail_from, to, subject
    m["Reply-To"] = reply_to or s.support_email
    m["Message-ID"] = make_msgid(domain="aiwazz.in")
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    return m


def _send_sync(msg: EmailMessage) -> None:
    s = get_settings()
    ctx = ssl.create_default_context()
    if s.smtp_host in ("127.0.0.1", "localhost"):
        ctx.check_hostname = False          # local Postfix presents the mail.aiwazz.in certificate
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        smtp.starttls(context=ctx)
        smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


async def send(msg: EmailMessage) -> bool:
    """Send now (awaitable). Returns False when mail is disabled or sending failed (logged, never raised)."""
    if not get_settings().mail_enabled:
        log.info("mail disabled, not sent: %s → %s", msg["Subject"], msg["To"])
        return False
    try:
        await asyncio.to_thread(_send_sync, msg)
        return True
    except Exception:  # noqa: BLE001
        log.exception("mail send failed: %s → %s", msg["Subject"], msg["To"])
        return False


def send_later(msg: EmailMessage) -> None:
    """Fire and forget (keeps a reference so the task isn't garbage-collected)."""
    t = asyncio.get_running_loop().create_task(send(msg))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def notify_support(request: Request | None, kind: str, data: dict) -> None:
    """Internal notice to support@ (contact form, invite request). Plain text only."""
    s = get_settings()
    title = {"invite_request": "New invite request", "contact": "New contact message"}.get(kind, kind)
    body = "\n".join(f"{k}: {v}" for k, v in data.items())
    send_later(build(s.support_email, f"[AiWazz] {title}", body + "\n", reply_to=data.get("email")))

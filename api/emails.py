"""Transactional email: templates (code defaults, editable in admin → Email), brand layout, sending log, suppression.

send_template() never raises: mail is off until the deliverability test passes (AIWAZZ_MAIL_ENABLED); every attempt
is logged in email_log with status sent | failed | disabled | suppressed, so staff can see what would have gone out.
"""
import html
import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import mailer
from settings import get_settings

log = logging.getLogger("aiwazz.mail")


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    subject: str
    body: str                    # plain text with {{variables}}; paragraphs separated by blank lines
    variables: tuple[str, ...]


DEFAULTS = {t.key: t for t in [
    Template("welcome", "Welcome", "Welcome to AiWazz",
             "Hi {{name}},\n\nYour AiWazz account is ready. Type it, hear it: open {{app_url}} and make your first voiceover.\n\n"
             "Questions? Just reply to this email.\n\n— AiWazz", ("name", "app_url")),
    Template("invite", "Invite", "Your AiWazz early-access invite",
             "Hi {{name}},\n\nYou're invited to AiWazz, AI voiceovers in Hindi, Hinglish and English.\n\n"
             "Your invite code: {{code}}\nSign up here: {{signup_url}}\n\n{{plan_note}}The code works once and expires on {{expires}}.\n\n— AiWazz",
             ("name", "code", "signup_url", "plan_note", "expires")),
    Template("invite_declined", "Invite request declined", "About your AiWazz invite request",
             "Hi {{name}},\n\nThanks for your interest in AiWazz. We can't offer you an invite right now, but we'll keep you in mind as we open up.\n\n— AiWazz",
             ("name",)),
    Template("verify_email", "Verify email", "Confirm your email for AiWazz",
             "Hi {{name}},\n\nConfirm your email address: {{link}}\n\nIf you didn't sign up, ignore this email.\n\n— AiWazz", ("name", "link")),
    Template("password_reset", "Password reset", "Reset your AiWazz password",
             "Hi {{name}},\n\nWe got a request to reset your password. Choose a new one here (the link works once, for 1 hour):\n{{link}}\n\n"
             "If you didn't ask for this, you can ignore this email; your password stays the same.\n\n— AiWazz", ("name", "link")),
    Template("payment_receipt", "Payment receipt", "Payment received: {{amount}}",
             "Hi {{name}},\n\nThanks! We received {{amount}} for the AiWazz {{plan}} plan. Invoice {{invoice_number}} is in Settings → Billing.\n\n— AiWazz",
             ("name", "amount", "plan", "invoice_number")),
    Template("payment_failed", "Payment failed", "Your AiWazz payment didn't go through",
             "Hi {{name}},\n\nWe couldn't charge your payment method for the {{plan}} plan. Razorpay will retry automatically. "
             "To keep your plan, update your payment method in Settings → Billing by {{grace_until}}.\n\n— AiWazz",
             ("name", "plan", "grace_until")),
    Template("plan_changed", "Plan changed", "Your AiWazz plan is now {{plan}}",
             "Hi {{name}},\n\nYour plan changed to {{plan}}{{until_note}}.\n\n— AiWazz", ("name", "plan", "until_note")),
    Template("subscription_cancelled", "Subscription cancelled", "Your AiWazz subscription is cancelled",
             "Hi {{name}},\n\nYour {{plan}} subscription is cancelled. You keep access until {{until}}; after that you're on the Free plan.\n\n— AiWazz",
             ("name", "plan", "until")),
    Template("account_deleted", "Account deleted", "Your AiWazz account was deleted",
             "Hi,\n\nYour AiWazz account and its history were deleted (reference {{reference}}). Invoices are kept for 8 years as tax law requires.\n\n— AiWazz",
             ("reference",)),
    Template("account_suspended", "Account paused", "Your AiWazz account is paused",
             "Hi {{name}},\n\nYour AiWazz account is paused. {{message}}\n\nIf you think this is a mistake, reply to this email.\n\n— AiWazz",
             ("name", "message")),
    Template("support_reply", "Support reply", "Re: {{subject}}",
             "Hi {{name}},\n\n{{body}}\n\n— {{agent}}, AiWazz support", ("name", "subject", "body", "agent")),
    Template("grievance_ack", "Grievance acknowledgement", "We received your complaint ({{reference}})",
             "Hi {{name}},\n\nWe received your complaint on {{received}} (reference {{reference}}). Our Grievance Officer will respond "
             "within 15 days, by {{due}}.\n\n— AiWazz", ("name", "reference", "received", "due")),
    Template("system_alert", "System alert (staff)", "[AiWazz alert] {{summary}}",
             "System health changed:\n\n{{lines}}\n\nDetails: https://login.aiwazz.in/admin/health\n\n— AiWazz monitoring",
             ("summary", "lines")),
    Template("dunning_reminder", "Payment reminder", "Action needed: your AiWazz plan",
             "Hi {{name}},\n\nYour last payment for the {{plan}} plan failed. Update your payment method in Settings → Billing by "
             "{{grace_until}}, or the account moves to the Free plan.\n\n— AiWazz", ("name", "plan", "grace_until")),
]}

_VAR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def fill(text: str, values: dict) -> str:
    return _VAR.sub(lambda m: str(values.get(m.group(1), "")), text)


def layout_html(body_text: str) -> str:
    """Brand layout: white card on Cloud, Midnight Navy text, AiWazz wordmark as text (no remote images)."""
    paras = "".join(
        f'<p style="margin:0 0 14px;line-height:1.55">{html.escape(p).replace(chr(10), "<br>")}</p>'
        for p in body_text.split("\n\n") if p.strip())
    paras = re.sub(r"(https://[^\s<]+)", r'<a href="\1" style="color:#2D36DB">\1</a>', paras)
    return (
        '<!doctype html><html><body style="margin:0;background:#F4F6FB;font-family:Inter,Segoe UI,Arial,sans-serif;color:#070D25">'
        '<div style="max-width:560px;margin:0 auto;padding:28px 16px">'
        '<p style="margin:0 0 16px;font:600 18px Poppins,Arial,sans-serif;color:#2D36DB">AiWazz</p>'
        f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:14px;padding:24px">{paras}</div>'
        '<p style="margin:16px 0 0;font-size:12px;color:#475569">© 2026 AiWazz · RADHAMADHAV WEBSTORE LLP · '
        '<a href="https://aiwazz.in/privacy-policy/" style="color:#475569">Privacy</a></p>'
        "</div></body></html>")


async def get_template(db: AsyncSession, key: str) -> tuple[str, str]:
    from models import EmailTemplate
    row = await db.get(EmailTemplate, key)
    d = DEFAULTS[key]
    return (row.subject, row.body) if row else (d.subject, d.body)


async def render(db: AsyncSession, key: str, values: dict) -> tuple[str, str, str]:
    subject, body = await get_template(db, key)
    text = fill(body, values)
    return fill(subject, values), text, layout_html(text)


async def send_template(db: AsyncSession, key: str, to: str, values: dict, *, user_id: int | None = None,
                        reply_to: str | None = None, headers: dict | None = None, attachments: list | None = None) -> str:
    """Render + send + log. Returns the email_log status. Caller commits (the log row is added to `db`)."""
    from models import EmailLog, EmailSuppression
    to = to.strip().lower()
    subject, text, html_ = await render(db, key, values)
    row = EmailLog(to_email=to, template=key, subject=subject[:200], user_id=user_id, status="queued",
                   message_id=(headers or {}).get("Message-ID", ""))
    db.add(row)
    if await db.get(EmailSuppression, to):
        row.status = "suppressed"
        return row.status
    if not get_settings().mail_enabled:
        row.status = "disabled"
        return row.status
    msg = mailer.build(to, subject, text, html_, reply_to=reply_to)
    for k, v in (headers or {}).items():
        del msg[k]
        msg[k] = v
    for data, filename in attachments or []:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    row.message_id = msg["Message-ID"]
    ok = await mailer.send(msg)
    row.status = "sent" if ok else "failed"
    return row.status

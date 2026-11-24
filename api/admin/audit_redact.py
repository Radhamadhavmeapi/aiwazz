"""Audit log privacy (owner decision, 25 Nov 2026): a deleted user's email stays in the audit log for 3 years after the
deletion, then is replaced by "sha256:<hash>" (same hash as deletion_log.email_hash, so it can still be matched when
someone gives their email). Runs daily; idempotent. On MariaDB the append-only trigger allows exactly this change
(see migration b8c9d0e1f2a3); nothing is ever deleted."""
import re
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import sha256
from db import utcnow
from models import AdminAudit, DeletionLog, User

RETENTION = timedelta(days=3 * 365)
_EMAIL = re.compile(r"[^@\s\"']+@[^@\s\"']+\.[a-z]{2,}", re.I)


def hashed(email: str) -> str:
    return "sha256:" + sha256(email.strip().lower())


async def sweep(db: AsyncSession) -> str:
    now = utcnow()
    live = set((await db.execute(select(User.email))).scalars())
    deleted_at = dict((await db.execute(select(DeletionLog.email_hash, DeletionLog.created_at))).all())
    rows = (await db.execute(select(AdminAudit))).scalars().all()
    due: set[str] = set()
    for r in rows:
        for field in (r.target_label, r.actor_email, r.before_json or "", r.after_json or "", r.reason):
            for e in _EMAIL.findall(field or ""):
                e = e.lower()
                if e in live:
                    continue
                when = deleted_at.get(sha256(e))
                if when is None:                    # no deletion record: count from this row's own age
                    when = r.at
                if when < now - RETENTION:
                    due.add(e)
    if not due:
        return "0 rows redacted"
    if db.bind.dialect.name == "mysql":
        await db.execute(text("SET @aiwazz_audit_redact = 1"))
    changed = 0
    try:
        for r in rows:
            def red(s: str | None) -> str | None:
                if not s:
                    return s
                return _EMAIL.sub(lambda m: hashed(m.group(0)) if m.group(0).lower() in due else m.group(0), s)
            new = {k: red(getattr(r, k)) for k in ("target_label", "actor_email", "before_json", "after_json", "reason")}
            if any(new[k] != getattr(r, k) for k in new):
                for k, v in new.items():
                    setattr(r, k, v[: AdminAudit.__table__.c[k].type.length] if v and getattr(AdminAudit.__table__.c[k].type, "length", None) else v)
                changed += 1
        await db.commit()
    finally:
        if db.bind.dialect.name == "mysql":
            await db.execute(text("SET @aiwazz_audit_redact = 0"))
    return f"{changed} rows redacted ({len(due)} email(s))"


__all__ = ["sweep", "hashed"]

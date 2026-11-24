"""Admin panel tables (phase 12, content/ADMIN-PANEL.md). All timestamps naive UTC."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, utcnow

__all__ = ["TotpSecret", "BackupCode", "AdminAudit", "AppSetting", "UserNote", "UserTag", "BonusGrant", "PasswordReset", "EmailTemplate", "EmailLog", "EmailSuppression"]


class TotpSecret(Base):
    """TOTP (RFC 6238) secret per staff member, encrypted with AIWAZZ_ADMIN_SECRET_KEY (Fernet). enabled_at NULL =
    enrolment started but not confirmed. last_step blocks reuse of a code (replay)."""
    __tablename__ = "totp_secrets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret_enc: Mapped[str] = mapped_column(String(255))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_step: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BackupCode(Base):
    """Single-use 2FA backup codes (10 per enrolment, shown once). Only SHA-256 of the normalised code is stored."""
    __tablename__ = "backup_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminAudit(Base):
    """Append-only audit log of staff actions. No FK on actor/target: rows outlive deleted accounts.
    On MariaDB, triggers reject UPDATE and DELETE (migration a8b1c2d3e4f5); the app has no code path that edits it."""
    __tablename__ = "admin_audit"
    __table_args__ = (Index("ix_admin_audit_at", "at"), Index("ix_admin_audit_target", "target_type", "target_id"),
                      Index("ix_admin_audit_actor", "actor_id", "at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_email: Mapped[str] = mapped_column(String(254), default="")
    actor_role: Mapped[str] = mapped_column(String(16), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)          # e.g. "user.plan.change", "mfa.verify.fail"
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    target_label: Mapped[str] = mapped_column(String(254), default="")
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")


class AppSetting(Base):
    """Runtime settings edited in the admin panel (JSON values; defaults in admin/settings_store.py)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UserNote(Base):
    """Internal staff note on a customer (never shown to the user)."""
    __tablename__ = "user_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_email: Mapped[str] = mapped_column(String(254), default="")
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserTag(Base):
    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_tags"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(32), index=True)


class BonusGrant(Base):
    """Extra characters for one usage cycle (period_start = start of that cycle, naive UTC). Negative = removal."""
    __tablename__ = "bonus_grants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chars: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(255))
    granted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordReset(Base):
    """One-time password reset link (only the SHA-256 of the token is stored; 1 hour; emailed, never shown to staff)."""
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailTemplate(Base):
    """Staff-edited override of a template in emails.DEFAULTS (no row = the default text)."""
    __tablename__ = "email_templates"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EmailLog(Base):
    __tablename__ = "email_log"
    __table_args__ = (Index("ix_email_log_created", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    to_email: Mapped[str] = mapped_column(String(254), index=True)
    template: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))       # queued | sent | failed | disabled | suppressed | bounced
    message_id: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(String(255), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailSuppression(Base):
    """Never email this address (hard bounce, unsubscribe or added by staff)."""
    __tablename__ = "email_suppressions"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    reason: Mapped[str] = mapped_column(String(32))       # hard_bounce | unsubscribe | manual
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

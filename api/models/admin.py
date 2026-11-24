"""Admin panel tables (phase 12, content/ADMIN-PANEL.md). All timestamps naive UTC."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, utcnow

__all__ = ["TotpSecret", "BackupCode", "AdminAudit", "AppSetting"]


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

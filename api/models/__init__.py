"""ORM models. All timestamps are naive UTC (see db.utcnow)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base, utcnow

ROLES = ("admin", "user")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Consent at signup (Terms, Privacy, Acceptable Use) + optional marketing
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    consent_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # Plan (legal/legal.json "plans"): free | starter | creator | pro. Set by billing later; for now manage.py set-plan.
    plan: Mapped[str] = mapped_column(String(16), default="free")
    # Optional end of a time-limited plan (naive UTC). After it, the user is on Free (effective_plan + hourly sweep).
    plan_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def effective_plan(self) -> str:
        """The plan that applies right now: an expired time-limited plan counts as Free even before the sweep runs."""
        if self.plan_until is not None and self.plan_until <= utcnow():
            return "free"
        return self.plan or "free"


class UserSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user: Mapped[User] = relationship(lazy="joined")


class Invite(Base):
    """Invite code for signup (invite-only). Only the SHA-256 of the normalised code is stored."""
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiKey(Base):
    """API key for scripts (header X-API-Key). Shown once; only the SHA-256 is stored."""
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16))          # first chars, shown in the UI
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped[User] = relationship(lazy="joined")


class Generation(Base):
    """One TTS job and its audio files (storage/audio/<id>.{mp3,wav}); owner-only access."""
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generations_user_created", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|error
    engine: Mapped[str] = mapped_column(String(16))
    voice: Mapped[str] = mapped_column(String(32))
    lang: Mapped[str] = mapped_column(String(4))
    speed: Mapped[float] = mapped_column(Float)
    format: Mapped[str] = mapped_column(String(4))
    loudness_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_chars: Mapped[int] = mapped_column(Integer)
    text_excerpt: Mapped[str] = mapped_column(String(160))   # for History; the full script is not stored
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    compute_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_lufs: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeletionLog(Base):
    """Proof that an account was deleted (reference ID shown to the user). No email in clear text."""
    __tablename__ = "deletion_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    email_hash: Mapped[str] = mapped_column(String(64), index=True)   # SHA-256 of the lowercase email
    generations_deleted: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContactMessage(Base):
    """Contact form on aiwazz.in/contact/ (read with manage.py list-messages)."""
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(String(4000))
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    handled: Mapped[bool] = mapped_column(Boolean, default=False)


class InviteRequest(Base):
    """"Request an invite" form on the signup page (read with manage.py list-requests). One row per email."""
    __tablename__ = "invite_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lowercase
    name: Mapped[str] = mapped_column(String(100), default="")
    use_case: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | invited | declined

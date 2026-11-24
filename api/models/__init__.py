"""ORM models. All timestamps are naive UTC (see db.utcnow)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base, utcnow

# Staff roles (admin panel, phase 12; permissions in admin/rbac.py) + "user" (customers).
STAFF_ROLES = ("owner", "admin", "support", "finance", "viewer")
ROLES = STAFF_ROLES + ("user",)


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
    # Billing details for GST invoices (state = 2-digit GST state code: place of supply)
    billing_name: Mapped[str] = mapped_column(String(150), default="", server_default="")
    billing_gstin: Mapped[str] = mapped_column(String(15), default="", server_default="")
    billing_state: Mapped[str] = mapped_column(String(2), default="", server_default="")
    billing_address: Mapped[str] = mapped_column(String(300), default="", server_default="")

    # Suspension (admin panel): the user sees a friendly message at login; reason is internal.
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    suspend_reason: Mapped[str] = mapped_column(String(255), default="", server_default="")
    name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_admin(self) -> bool:
        """Product-level admin (unlimited usage, admin-only voices): owner + admin. Panel permissions: admin/rbac.py."""
        return self.role in ("owner", "admin")

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

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
    # Admin panel: 2FA verified for THIS session (idle timeout via admin_seen_at), step-up window, impersonation.
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admin_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stepup_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    impersonate_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impersonate_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    # Early-access friends: the account starts on this plan until plan_until (admin panel → Invites).
    plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plan_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str] = mapped_column(String(254), default="", server_default="")   # set when made for a waitlist entry


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
    style: Mapped[str | None] = mapped_column(String(32), nullable=True)   # tts/styles.py id
    transliterate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # Hinglish toggle (analytics)
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
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invite_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ── Billing (Razorpay Subscriptions). Invoices and payments outlive the account (8-year tax records). ──
class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    rzp_subscription_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(8))          # monthly | yearly
    status: Mapped[str] = mapped_column(String(16), default="created")  # Razorpay status
    current_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Plan changes (admin panel A3): upgrades apply now (Razorpay prorates), downgrades at the period end.
    rzp_plan_id: Mapped[str] = mapped_column(String(40), default="", server_default="")
    pending_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pending_period: Mapped[str | None] = mapped_column(String(8), nullable=True)
    coupon_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    rzp_payment_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    refunded_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str] = mapped_column(String(255), default="", server_default="")   # failed payments: Razorpay reason


class Invoice(Base):
    """GST tax invoice. Buyer details are a snapshot taken at payment time."""
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    plan: Mapped[str] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(8))
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    buyer_name: Mapped[str] = mapped_column(String(150))
    buyer_email: Mapped[str] = mapped_column(String(254))
    buyer_gstin: Mapped[str] = mapped_column(String(15), default="")
    buyer_state: Mapped[str] = mapped_column(String(2))
    buyer_address: Mapped[str] = mapped_column(String(300), default="")
    taxable_paise: Mapped[int] = mapped_column(Integer)
    cgst_paise: Mapped[int] = mapped_column(Integer, default=0)
    sgst_paise: Mapped[int] = mapped_column(Integer, default=0)
    igst_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # cancelled by a full credit note


class InvoiceCounter(Base):
    """One row per Indian financial year ("2026-27"); the next invoice number is last + 1 (row locked)."""
    __tablename__ = "invoice_counters"
    fy: Mapped[str] = mapped_column(String(7), primary_key=True)
    last: Mapped[int] = mapped_column(Integer, default=0)


class WebhookEvent(Base):
    """Every Razorpay webhook received (x-razorpay-event-id; retries handled once). Bad signatures are logged too
    (id "badsig:…", payload kept for diagnosis, never processed). Replay re-runs the stored payload (idempotent)."""
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    signature_ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    status: Mapped[str] = mapped_column(String(16), default="processed", server_default="processed")  # processed|failed|ignored|rejected
    note: Mapped[str] = mapped_column(String(255), default="", server_default="")
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    replays: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Pronunciation(Base):
    """Pronunciation fix: `word` (case-insensitive, whole word) is read as `say_as`. user_id NULL = global (admin) list.
    Uniqueness of (user_id, word_key) is also checked in code, since NULLs don't collide in a unique index."""
    __tablename__ = "pronunciations"
    __table_args__ = (UniqueConstraint("user_id", "word_key", name="uq_pronunciations_user_word"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    word: Mapped[str] = mapped_column(String(64))
    word_key: Mapped[str] = mapped_column(String(64))      # lowercase, single spaces
    say_as: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class VoiceConsent(Base):
    """Consent / source record for a custom (clone) voice (phase 13). A clone voice is selectable only while it has an
    `active` record. real_person needs a signed document (`pending` until uploaded); ai_voice needs an owner attestation.
    Revoking disables the voice at once and deletes its reference audio + cached tone colour (manage.py)."""
    __tablename__ = "voice_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voice_id: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(16))           # real_person | ai_voice
    speaker_name: Mapped[str] = mapped_column(String(150), default="")   # or the tool name, if known
    consent_scope: Mapped[str] = mapped_column(String(255), default="")
    signed_document_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # private, on the server
    attestation_note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | active | revoked
    date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


from .admin import *  # noqa: E402,F401,F403  (admin panel tables)

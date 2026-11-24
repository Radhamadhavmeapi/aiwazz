"""Admin panel tables (phase 12, content/ADMIN-PANEL.md). All timestamps naive UTC."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, utcnow

__all__ = ["TotpSecret", "BackupCode", "AdminAudit", "AppSetting", "UserNote", "UserTag", "BonusGrant", "PasswordReset", "EmailTemplate", "EmailLog", "EmailSuppression",
           "Refund", "CreditNote", "CreditNoteCounter", "DunningCase", "PlanVersion", "Coupon", "CouponRedemption",
           "ReferralCode", "Referral", "TaskRun", "Ticket", "TicketMessage", "CannedReply", "ModerationRule", "Flag",
           "BlockEntry", "VoiceSetting", "StyleSetting", "RateOverride"]


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


# ── Billing (A3) ────────────────────────────────────────────────────────────
class Refund(Base):
    """Full or partial refund of a payment (Razorpay). Each processed refund gets a GST credit note."""
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rzp_refund_id: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending | processed | failed
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    credit_note_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CreditNote(Base):
    """GST credit note (CGST s.34) against one invoice: refund or void. Series AWZ-CN/<FY>/<n>, never renumbered."""
    __tablename__ = "credit_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    refund_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8))                        # refund | void
    reason: Mapped[str] = mapped_column(String(255))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    taxable_paise: Mapped[int] = mapped_column(Integer)
    cgst_paise: Mapped[int] = mapped_column(Integer, default=0)
    sgst_paise: Mapped[int] = mapped_column(Integer, default=0)
    igst_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)


class CreditNoteCounter(Base):
    __tablename__ = "credit_note_counters"
    fy: Mapped[str] = mapped_column(String(7), primary_key=True)
    last: Mapped[int] = mapped_column(Integer, default=0)


class DunningCase(Base):
    """A subscription whose payment failed: reminder emails on day 0/3/7, then Free after the grace period."""
    __tablename__ = "dunning_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    grace_until: Mapped[datetime] = mapped_column(DateTime)
    failures: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(String(255), default="")
    emails_sent: Mapped[str] = mapped_column(String(32), default="")    # "0,3,7"
    status: Mapped[str] = mapped_column(String(16), default="open")     # open | resolved | downgraded
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlanVersion(Base):
    """Razorpay plans are immutable: every price change creates a new version. Subscribers keep the plan id they
    signed up with (grandfathered) unless migrated explicitly. active = offered to new subscribers."""
    __tablename__ = "plan_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan: Mapped[str] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(8))
    taxable_paise: Mapped[int] = mapped_column(Integer)
    total_paise: Mapped[int] = mapped_column(Integer)
    rzp_plan_id: Mapped[str] = mapped_column(String(40), default="")    # empty until created in Razorpay
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Coupon(Base):
    """Discount code. Applied through a Razorpay Offer (offer_id on the subscription; offers are created in the
    Razorpay Dashboard, the API can't create them) and validated here (plan, period, dates, limits)."""
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)          # uppercase
    description: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(8))                        # percent | fixed
    value: Mapped[int] = mapped_column(Integer)                         # percent (1-100) or paise
    plans: Mapped[str] = mapped_column(String(64), default="")          # "" = all, else "starter,creator"
    periods: Mapped[str] = mapped_column(String(16), default="monthly,yearly")
    duration: Mapped[str] = mapped_column(String(8), default="once")    # once (first payment) | cycles
    cycles: Mapped[int] = mapped_column(Integer, default=1)
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    rzp_offer_id: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending (checkout) | redeemed | void
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferralCode(Base):
    """Referral program data model (user-facing part behind the "referrals" feature flag, off)."""
    __tablename__ = "referral_codes"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referred_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="signed_up")   # signed_up | converted | rewarded
    reward_chars: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TaskRun(Base):
    """Background task log (scheduler.py): every run of every task, so failures are visible in the admin panel."""
    __tablename__ = "task_runs"
    __table_args__ = (Index("ix_task_runs_task_started", "task", "started_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | ok | failed
    detail: Mapped[str] = mapped_column(String(500), default="")


# ── Support inbox (A4) ──────────────────────────────────────────────────────
class Ticket(Base):
    """One conversation in the support inbox: contact form, invite request, grievance or misuse report.
    Grievances carry the legal timelines (acknowledge within 24 h, resolve within 15 days)."""
    __tablename__ = "tickets"
    __table_args__ = (Index("ix_tickets_status_updated", "status", "updated_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))                       # contact | invite_request | grievance | abuse | billing
    status: Mapped[str] = mapped_column(String(16), default="new")      # new | open | waiting | resolved
    priority: Mapped[str] = mapped_column(String(8), default="normal")  # low | normal | high | urgent
    assignee_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(254), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # contact_messages.id / invite_requests.id
    reference: Mapped[str] = mapped_column(String(24), unique=True)        # shown to the sender, e.g. AWZ-T-000123
    thread_message_id: Mapped[str] = mapped_column(String(200), default="")   # Message-ID of our first email (threading)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ack_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)      # grievances: +24 h
    resolve_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # grievances: +15 days


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(8))                   # in | out | note (internal)
    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_email: Mapped[str] = mapped_column(String(254), default="")
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(String(200), default="")
    email_status: Mapped[str] = mapped_column(String(16), default="")  # out: sent | disabled | failed | suppressed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CannedReply(Base):
    __tablename__ = "canned_replies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ── Moderation & trust (A4) ─────────────────────────────────────────────────
class ModerationRule(Base):
    """Pattern checked against every script at submit time. action flag = allow + review; block = refuse the job."""
    __tablename__ = "moderation_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(24))                   # impersonation | scam | threat | explicit | other
    kind: Mapped[str] = mapped_column(String(8), default="keywords")    # keywords (comma separated, whole words) | regex
    pattern: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(8), default="medium")  # low | medium | high
    action: Mapped[str] = mapped_column(String(8), default="flag")      # flag | block
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Flag(Base):
    """Something to review: a rule match on a script, a volume spike, many accounts from one IP, or a public report.
    Stores the matched term only (not the script); the script is viewable under the privacy rule."""
    __tablename__ = "flags"
    __table_args__ = (Index("ix_flags_status_created", "status", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))                     # rule | volume | multi_account | report
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_name: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str] = mapped_column(String(24), default="other")
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    matched: Mapped[str] = mapped_column(String(100), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)       # the job was refused
    status: Mapped[str] = mapped_column(String(16), default="open")     # open | dismissed | actioned
    action: Mapped[str] = mapped_column(String(32), default="")         # warned | suspended | audio_deleted | reported
    note: Mapped[str] = mapped_column(String(500), default="")
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BlockEntry(Base):
    """Blocklist: email address, email domain or IP (or CIDR). Blocks signup and invite requests."""
    __tablename__ = "blocklist"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_blocklist"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))                        # email | domain | ip
    value: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ── Voices, styles, API limits (A5) ─────────────────────────────────────────
class VoiceSetting(Base):
    """Admin overrides for a catalogue voice (tts/voices.py or a clone voice). No row = defaults."""
    __tablename__ = "voice_settings"
    voice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_name: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(String(120), default="")     # the short tone line on voice cards
    tags: Mapped[str] = mapped_column(String(200), default="")            # comma separated: gender, accent, tone…
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    min_plan: Mapped[str] = mapped_column(String(16), default="free")     # free | starter | creator | pro
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StyleSetting(Base):
    __tablename__ = "style_settings"
    style_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_name: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(String(160), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RateOverride(Base):
    """Per-key or per-user API rate limit (requests per minute) replacing the default."""
    __tablename__ = "rate_overrides"
    __table_args__ = (UniqueConstraint("scope", "target_id", name="uq_rate_overrides"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(8))                        # key | user
    target_id: Mapped[int] = mapped_column(Integer)
    rpm: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

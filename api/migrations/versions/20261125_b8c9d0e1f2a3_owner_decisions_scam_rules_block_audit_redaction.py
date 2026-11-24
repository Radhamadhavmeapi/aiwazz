"""owner decisions 25 Nov 2026: bank/OTP/KYC scam rules block; audit log redaction after 3 years

- moderation_rules "OTP / KYC scam phrases" and "Impersonating officials or banks" → action = block
- admin_audit UPDATE trigger: still refuses every change, except the 3-year redaction sweep (admin/audit_redact.py),
  which sets @aiwazz_audit_redact = 1 on its connection and may only change target_label, actor_email, before_json,
  after_json and reason (every other column must stay identical). DELETE stays refused.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-25 09:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BLOCKED = ("OTP / KYC scam phrases", "Impersonating officials or banks")
REDACT_TRIGGER = """
CREATE TRIGGER admin_audit_no_update BEFORE UPDATE ON admin_audit FOR EACH ROW
BEGIN
  IF NOT (COALESCE(@aiwazz_audit_redact, 0) = 1
          AND NEW.id <=> OLD.id AND NEW.at <=> OLD.at AND NEW.actor_id <=> OLD.actor_id
          AND NEW.actor_role <=> OLD.actor_role AND NEW.action <=> OLD.action AND NEW.target_type <=> OLD.target_type
          AND NEW.target_id <=> OLD.target_id AND NEW.ip <=> OLD.ip AND NEW.user_agent <=> OLD.user_agent) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'admin_audit is append-only';
  END IF;
END
"""


def upgrade() -> None:
    for name in BLOCKED:
        op.execute(f"UPDATE moderation_rules SET action = 'block' WHERE name = '{name}'")
    if op.get_bind().dialect.name == "mysql":
        op.execute("DROP TRIGGER IF EXISTS admin_audit_no_update")
        op.execute(REDACT_TRIGGER)


def downgrade() -> None:
    for name in BLOCKED:
        op.execute(f"UPDATE moderation_rules SET action = 'flag' WHERE name = '{name}'")
    if op.get_bind().dialect.name == "mysql":
        op.execute("DROP TRIGGER IF EXISTS admin_audit_no_update")
        op.execute("CREATE TRIGGER admin_audit_no_update BEFORE UPDATE ON admin_audit FOR EACH ROW "
                   "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'admin_audit is append-only'")

"""Owner decisions 25 Nov 2026: audit emails of deleted accounts → SHA-256 after 3 years; alerts to the owner only;
bank/OTP/KYC scam rules block (data migration b8c9d0e1f2a3)."""
from datetime import timedelta
from pathlib import Path

from tests.conftest import run_db


def test_audit_emails_of_deleted_accounts_hashed_after_3_years(app_env):
    from sqlalchemy import select

    from admin import audit_redact
    from auth.security import sha256
    from db import utcnow
    from models import AdminAudit, DeletionLog, User

    old = utcnow() - timedelta(days=3 * 365 + 5)

    async def setup(db):
        db.add(User(email="alive@example.com", password_hash="x"))
        db.add(DeletionLog(reference="DEL-1", email_hash=sha256("gone@example.com"), created_at=old))
        db.add(DeletionLog(reference="DEL-2", email_hash=sha256("recent@example.com"), created_at=utcnow() - timedelta(days=200)))
        db.add(AdminAudit(at=old, actor_email="alive@example.com", actor_role="admin", action="user.delete", target_type="user",
                          target_id="7", target_label="gone@example.com", reason="asked by Gone@Example.com",
                          before_json='{"owner": "gone@example.com"}'))
        db.add(AdminAudit(at=old, actor_email="alive@example.com", actor_role="admin", action="user.plan.change", target_type="user",
                          target_id="8", target_label="recent@example.com"))
        db.add(AdminAudit(at=utcnow(), actor_email="alive@example.com", actor_role="admin", action="user.note.add", target_type="user",
                          target_id="7", target_label="gone@example.com"))
    run_db(app_env, setup)
    assert run_db(app_env, audit_redact.sweep) == "2 rows redacted (1 email(s))"

    async def rows(db):
        return [(r.target_label, r.actor_email, r.reason, r.before_json) for r in (await db.execute(select(AdminAudit).order_by(AdminAudit.id))).scalars()]
    r = run_db(app_env, rows)
    h = "sha256:" + sha256("gone@example.com")
    assert r[0] == (h, "alive@example.com", f"asked by {h}", '{"owner": "' + h + '"}')   # 3+ years after deletion: hashed
    assert r[1][0] == "recent@example.com"                                                # deleted 200 days ago: kept
    assert r[2][0] == h                                                                   # same deleted email, newer row: hashed too
    assert run_db(app_env, audit_redact.sweep) == "0 rows redacted"                        # idempotent


def test_alerts_go_to_owner_only(staff, monkeypatch, app_env):
    from collections import namedtuple

    from admin import health
    monkeypatch.setattr(health, "ssl_expiry", lambda h: {"host": h, "ok": True, "days_left": 60})
    DU = namedtuple("DU", "total used free")
    monkeypatch.setattr(health.shutil, "disk_usage", lambda p: DU(100, 95, 5))
    o, a = staff("owner"), staff("admin")
    o.post("/api/admin/system/alerts/check")
    from sqlalchemy import select

    from models import EmailLog

    async def to(db):
        return [e.to_email for e in (await db.execute(select(EmailLog))).scalars()]
    assert run_db(app_env, to) == [o.email]


def test_scam_rule_migration_targets_the_seeded_rules():
    root = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    seed = next(root.glob("*d4e5f6a7b8c9*")).read_text()
    mig = next(root.glob("*b8c9d0e1f2a3*")).read_text()
    for name in ("OTP / KYC scam phrases", "Impersonating officials or banks"):
        assert f'("{name}"' in seed and name in mig
    assert "Threats and violence" not in mig and "Explicit content" not in mig

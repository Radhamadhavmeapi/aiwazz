"""Roles → permissions. Checked server-side on every /api/admin endpoint (admin/deps.require_perm).

owner    everything; the only role that can change roles, transfer ownership or touch secrets
admin    everything except roles / ownership / secrets
support  users (read), invites + waitlist, support inbox, moderation (content under the privacy rule)
finance  billing, invoices, GST exports, refunds, plans (read), coupons
viewer   read-only dashboards (overview, analytics, health, queue)
"""
from models import STAFF_ROLES

# Every permission the panel knows. Endpoints use exactly these strings (a typo fails at import time, see require_perm).
PERMS = frozenset({
    "overview.read", "analytics.read", "audit.read",
    "users.read", "users.write", "users.delete", "users.impersonate", "users.content", "users.export", "users.bulk",
    "invites.read", "invites.write",
    "support.read", "support.write",
    "moderation.read", "moderation.write",
    "billing.read", "billing.write", "billing.refund", "billing.export",
    "plans.read", "plans.write", "coupons.read", "coupons.write",
    "voices.read", "voices.write", "pronunciations.write",
    "api.read", "api.write",
    "queue.read", "queue.write", "maintenance.write",
    "system.read", "system.write", "logs.read", "backups.read", "backups.download",
    "email.read", "email.write", "announcements.read", "announcements.write",
    "compliance.read", "compliance.write", "legal.write",
    "settings.read", "settings.write", "settings.secrets", "payments.mode",
    "team.read", "roles.write", "ownership.transfer",
    "export",           # CSV export of any list (also needs the list's own read permission)
})

_OWNER_ONLY = {"roles.write", "ownership.transfer", "settings.secrets", "payments.mode"}
_VIEWER = {"overview.read", "analytics.read", "system.read", "queue.read"}

ROLE_PERMS: dict[str, frozenset[str]] = {
    "owner": PERMS,
    "admin": PERMS - _OWNER_ONLY,
    "support": frozenset(_VIEWER - {"system.read"} | {
        "users.read", "users.content", "invites.read", "invites.write", "support.read", "support.write",
        "moderation.read", "moderation.write", "announcements.read", "compliance.read", "email.read"}),
    "finance": frozenset(_VIEWER - {"system.read", "queue.read"} | {
        "users.read", "billing.read", "billing.write", "billing.refund", "billing.export", "plans.read",
        "coupons.read", "coupons.write", "compliance.read", "export"}),
    "viewer": frozenset(_VIEWER),
}
assert set(ROLE_PERMS) == set(STAFF_ROLES)
assert all(p <= PERMS for p in ROLE_PERMS.values())


def perms_for(role: str) -> frozenset[str]:
    return ROLE_PERMS.get(role, frozenset())


def has(role: str, perm: str) -> bool:
    return perm in perms_for(role)

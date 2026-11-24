"""A1 security foundation: 404 for non-staff, mandatory 2FA, backup codes, replay, idle lock, step-up, audit,
IP allowlist, sign out admin sessions, and an automatic role x endpoint permission matrix."""
from datetime import timedelta

import pytest

from tests.conftest import PW, identity, login, new_client, run_db, stepup


def test_non_staff_get_plain_404(client, anon):
    unknown = client.get("/api/admin/definitely-not-a-route")
    for path in ("/api/admin/me", "/api/admin/audit", "/api/admin/settings/security"):
        r = client.get(path)                                   # signed-in regular user
        assert r.status_code == 404 and r.json() == unknown.json() == {"detail": "Not Found"}
        with identity(client):                                  # signed out
            assert client.get(path).status_code == 404
    r = client.post("/api/admin/mfa/verify", json={"code": "123456"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 404                                 # 404 even before the CSRF check


def test_staff_api_key_is_404(staff, set_plan):
    c = staff("admin")
    key = c.post("/api/keys", json={"name": "k"}).json()["key"]
    with identity(c) as anon:
        assert anon.get("/api/admin/me", headers={"X-API-Key": key}).status_code == 404


def test_2fa_setup_flow(anon, make_invite, clock):
    make_invite("STAF-0001", role="support")
    c = new_client(anon.app, share=anon)
    assert c.post("/api/auth/signup", json={"email": "s@example.com", "password": PW, "invite_code": "STAF-0001",
                                            "accept_terms": True}).status_code == 201
    c.headers["X-CSRF-Token"] = c.cookies.get("__Host-aiwazz_csrf")
    me = c.get("/api/admin/me").json()
    assert me["mfa"] == {"enrolled": False, "unlocked": False, "backup_codes_left": 0, "configured": True}
    assert me["perms"] == []
    r = c.get("/api/admin/audit")
    assert r.status_code == 401 and r.headers["x-admin-lock"] == "setup"
    assert c.post("/api/admin/mfa/setup", json={"password": "wrong password"}).status_code == 422
    r = c.post("/api/admin/mfa/setup", json={"password": PW})
    assert r.status_code == 200 and r.json()["qr_svg"].startswith("<svg") and "otpauth://totp/" in r.json()["otpauth_uri"]
    secret = r.json()["secret"]
    assert c.post("/api/admin/mfa/enable", json={"code": "000000"}).status_code == 422
    r = c.post("/api/admin/mfa/enable", json={"code": clock.code(secret)})
    codes = r.json()["backup_codes"]
    assert r.status_code == 200 and len(codes) == 10 and len(set(codes)) == 10
    me = c.get("/api/admin/me").json()
    assert me["mfa"]["unlocked"] and "support.read" in me["perms"] and "billing.read" not in me["perms"]
    assert c.post("/api/admin/mfa/setup", json={"password": PW}).status_code == 409   # can't silently re-enrol


def test_secrets_stored_encrypted_and_codes_hashed(staff, app_env):
    c = staff("admin")
    from sqlalchemy import select

    from models import BackupCode, TotpSecret

    async def q(db):
        t = (await db.execute(select(TotpSecret))).scalars().one()
        bc = (await db.execute(select(BackupCode))).scalars().all()
        return t.secret_enc, [b.code_hash for b in bc]
    enc, hashes = run_db(app_env, q)
    assert c.secret not in enc and len(hashes) == 10
    assert not any(code in h for code in c.backup_codes for h in hashes)


def test_lock_verify_replay_and_backup_codes(staff, clock):
    c = staff("admin")
    assert c.post("/api/admin/lock").status_code == 200
    assert c.get("/api/admin/audit").headers.get("x-admin-lock") == "verify"
    code = clock.code(c.secret)
    assert c.post("/api/admin/mfa/verify", json={"code": code}).status_code == 200
    assert c.get("/api/admin/audit").status_code == 200
    c.post("/api/admin/lock")
    assert c.post("/api/admin/mfa/verify", json={"code": code}).status_code == 422     # same code again: replay
    bc = c.backup_codes[0]
    r = c.post("/api/admin/mfa/verify", json={"code": bc.upper()})
    assert r.status_code == 200 and r.json() == {"ok": True, "method": "backup", "backup_codes_left": 9}
    c.post("/api/admin/lock")
    assert c.post("/api/admin/mfa/verify", json={"code": bc}).status_code == 422       # single use


def test_verify_rate_limited(staff):
    c = staff("viewer")
    c.post("/api/admin/lock")
    codes = [c.post("/api/admin/mfa/verify", json={"code": "111111"}).status_code for _ in range(6)]
    assert codes[:5] == [422] * 5 and codes[5] == 429


def test_idle_timeout_and_max_age(staff, app_env):
    from sqlalchemy import update

    from db import utcnow
    from models import UserSession
    c = staff("admin")
    assert c.get("/api/admin/audit").status_code == 200

    async def age(db, **kw):
        await db.execute(update(UserSession).values(**kw))
    run_db(app_env, lambda db: age(db, admin_seen_at=utcnow() - timedelta(minutes=31)))
    assert c.get("/api/admin/audit").headers.get("x-admin-lock") == "verify"
    run_db(app_env, lambda db: age(db, admin_seen_at=utcnow(), mfa_at=utcnow() - timedelta(hours=13)))
    assert c.get("/api/admin/audit").headers.get("x-admin-lock") == "verify"


def test_stepup_required_and_expires(staff, clock, app_env, anon):
    c = staff("owner")
    body = {"enabled": False, "cidrs": []}
    r = c.put("/api/admin/settings/security", json=body)
    assert r.status_code == 403 and r.headers["x-step-up"] == "required"
    assert c.post("/api/admin/stepup", json={"password": "nope nope", "code": clock.code(c.secret)}).status_code == 422
    stepup(c, clock)
    assert c.put("/api/admin/settings/security", json=body).status_code == 200
    from sqlalchemy import update

    from db import utcnow
    from models import UserSession

    async def expire(db):
        await db.execute(update(UserSession).values(stepup_until=utcnow() - timedelta(seconds=1)))
    run_db(app_env, expire)
    assert c.put("/api/admin/settings/security", json=body).status_code == 403


def test_audit_log_records_and_cannot_be_edited(staff, clock):
    c = staff("owner")
    c.post("/api/admin/lock")
    c.post("/api/admin/mfa/verify", json={"code": "999999"})          # failure is logged too
    c.post("/api/admin/mfa/verify", json={"code": clock.code(c.secret)})
    stepup(c, clock)
    c.put("/api/admin/settings/security", json={"enabled": False, "cidrs": ["10.0.0.0/8"]})
    items = c.get("/api/admin/audit?size=50").json()["items"]
    actions = [i["action"] for i in items]
    for a in ("mfa.enable", "admin.lock", "mfa.verify.fail", "mfa.verify", "stepup", "settings.security.ip_allowlist"):
        assert a in actions, a
    row = next(i for i in items if i["action"] == "settings.security.ip_allowlist")
    assert row["actor_email"] == c.email and row["actor_role"] == "owner" and "10.0.0.0/8" in row["after"]
    assert c.get("/api/admin/audit?action=mfa.verify").json()["total"] >= 2
    # No route edits or deletes the log
    for method, path, _ in admin_routes():
        if path.startswith("/api/admin/audit"):
            assert method == "GET"


def test_csv_export_needs_stepup_and_is_audited(staff, clock):
    c = staff("owner")
    r = c.get("/api/admin/audit?format=csv")
    assert r.status_code == 403 and r.headers.get("x-step-up") == "required"
    stepup(c, clock)
    r = c.get("/api/admin/audit?format=csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "action" in r.text
    assert c.get("/api/admin/audit?action=export.csv").json()["total"] == 1
    support = staff("support")
    assert support.get("/api/admin/audit?format=csv").status_code == 403


def test_ip_allowlist(staff, clock, app_env):
    from admin.deps import ip_allowed
    assert ip_allowed("203.0.113.7", ["203.0.113.0/24"]) and not ip_allowed("198.51.100.1", ["203.0.113.0/24"])
    assert not ip_allowed("garbage", ["0.0.0.0/0"])
    c = staff("owner")
    stepup(c, clock)
    r = c.put("/api/admin/settings/security", json={"enabled": True, "cidrs": ["203.0.113.0/24"]})
    assert r.status_code == 422 and "lock you out" in r.json()["detail"]
    assert c.put("/api/admin/settings/security", json={"enabled": True, "cidrs": ["not-an-ip"]}).status_code == 422
    # Force-enable it in the DB: the test client's address isn't in the list → plain 404
    import json

    from admin import settings_store
    from models import AppSetting

    async def put(db):
        db.add(AppSetting(key="security.admin_ip_allowlist", value_json=json.dumps({"enabled": True, "cidrs": ["203.0.113.0/24"]})))
    run_db(app_env, put)
    settings_store.clear_cache()
    assert c.get("/api/admin/me").status_code == 404


def test_sign_out_other_admin_sessions(staff, anon, clock):
    c = staff("admin")
    other = new_client(anon.app, share=anon)
    login(other, c.email)
    other.post("/api/admin/mfa/verify", json={"code": clock.code(c.secret)})
    assert other.get("/api/admin/audit").status_code == 200
    r = c.post("/api/admin/sessions/sign-out-admin", json={"scope": "mine"})
    assert r.status_code == 200 and r.json()["sessions"] == 1
    assert other.get("/api/admin/audit").headers.get("x-admin-lock") == "verify"
    assert c.get("/api/admin/audit").status_code == 200        # this one stays unlocked
    assert other.get("/api/auth/me").status_code == 200        # the normal app session is untouched
    assert c.post("/api/admin/sessions/sign-out-admin", json={"scope": "all_staff"}).status_code == 403  # owner only


def test_owner_cannot_delete_own_account(staff):
    c = staff("owner")
    r = c.post("/api/auth/delete-account", json={"password": PW, "confirm": "DELETE"})
    assert r.status_code == 422 and "Transfer ownership" in r.json()["detail"]


def test_owner_and_admin_are_product_admins_others_not(staff):
    assert staff("owner").get("/api/usage").json()["unlimited"] is True
    assert staff("admin").get("/api/usage").json()["unlimited"] is True
    assert staff("support").get("/api/usage").json()["unlimited"] is False


# ── Automatic permission matrix: every /api/admin route × every staff role ──────────────────────────────────────
SESSION_ROUTES = {"/api/admin/me", "/api/admin/mfa/setup", "/api/admin/mfa/enable", "/api/admin/mfa/verify",
                  "/api/admin/lock", "/api/admin/stepup", "/api/admin/mfa/backup-codes",
                  "/api/admin/sessions/sign-out-admin", "/api/admin/impersonate/stop"}


def _route_perms(route) -> set[str] | None:
    found: set[str] = set()
    has_perm = False

    def walk(dep):
        nonlocal has_perm
        perms = getattr(dep.call, "perms", None)
        if perms is not None:
            has_perm = True
            found.update(perms)
        for d in dep.dependencies:
            walk(d)
    walk(route.dependant)
    return found if has_perm else None


def _flat(routes):
    for r in routes:
        if hasattr(r, "effective_route_contexts"):        # FastAPI ≥ 0.160: included routers are resolved lazily
            yield from r.effective_route_contexts()
        else:
            yield r


def admin_routes():
    from main import app
    out = []
    for r in _flat(app.routes):
        path = getattr(r, "path", "")
        if path.startswith("/api/admin") and getattr(r, "dependant", None) is not None:
            for m in sorted((r.methods or set()) - {"HEAD"}):
                out.append((m, path, r))
    assert out, "no admin routes found"
    return out


def test_every_admin_route_checks_a_permission():
    missing = [f"{m} {p}" for m, p, r in admin_routes() if _route_perms(r) is None and p not in SESSION_ROUTES]
    assert not missing, f"admin routes without require_perm: {missing}"


def test_permission_matrix(staff, clock):
    import re

    from admin import rbac
    clients = {role: staff(role) for role in rbac.ROLE_PERMS}
    checked = 0
    for method, path, route in admin_routes():
        needed = _route_perms(route)
        if not needed:
            continue
        url = re.sub(r"\{[^}]+\}", "1", path)
        for role, c in clients.items():
            r = c.request(method, url, json={} if method != "GET" else None)
            allowed = needed <= rbac.ROLE_PERMS[role]
            denied = r.status_code == 403 and "x-step-up" not in r.headers
            assert denied != allowed, f"{role} {method} {path}: {r.status_code} {r.text[:120]}"
            assert r.status_code != 401, f"{role} {method} {path} locked: {r.text}"
            checked += 1
    assert checked > 0

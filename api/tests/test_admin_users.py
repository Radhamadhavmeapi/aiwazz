"""A2: overview, users (list, detail, actions, privacy rule, impersonation, export, delete), invites + waitlist,
signup mode, search, notifications."""
from datetime import date, timedelta

from tests.conftest import PW, identity, new_client, run_db, signup, stepup


def _customer(anon, make_invite, email="cust@example.com", code="CUST-0001"):
    make_invite(code)
    c = new_client(anon.app, share=anon)
    assert signup(c, email=email, password=PW, code=code).status_code == 201
    uid = c.get("/api/auth/me").json()["id"]
    return c, uid


def test_users_list_filters_sort_and_export(staff, anon, make_invite, clock):
    a = staff("admin")
    _, uid = _customer(anon, make_invite)
    page = a.get("/api/admin/users?q=cust").json()
    assert page["total"] == 1 and page["items"][0]["id"] == uid and page["items"][0]["status"] == "active"
    assert a.get(f"/api/admin/users?q={uid}").json()["total"] >= 1
    assert a.get("/api/admin/users?role=staff").json()["total"] == 1
    assert a.get("/api/admin/users?plan=pro").json()["total"] == 0
    assert a.get("/api/admin/users?sort=-chars").status_code == 200
    assert a.get("/api/admin/users?sort=password_hash").status_code == 422      # sort whitelist
    stepup(a, clock)
    csv = a.get("/api/admin/users?format=csv")
    assert csv.status_code == 200 and "cust@example.com" in csv.text and "password" not in csv.text


def test_change_plan_needs_stepup_and_is_audited(staff, anon, make_invite, clock):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    body = {"plan": "creator", "until": (date.today() + timedelta(days=90)).isoformat(), "reason": "early access friend"}
    r = a.put(f"/api/admin/users/{uid}/plan", json=body)
    assert r.status_code == 403 and r.headers["x-step-up"] == "required"
    stepup(a, clock)
    assert a.put(f"/api/admin/users/{uid}/plan", json=body).status_code == 200
    assert c.get("/api/usage").json()["plan"] == "creator"
    entry = a.get(f"/api/admin/audit?action=user.plan.change&target_id={uid}").json()["items"][0]
    assert '"free"' in entry["before"] and '"creator"' in entry["after"] and entry["reason"] == "early access friend"
    assert a.put(f"/api/admin/users/{uid}/plan", json=body | {"plan": "free"}).status_code == 422   # end date needs paid plan


def test_bonus_characters_raise_allowance(staff, anon, make_invite):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    before = c.get("/api/usage").json()["allowance"]
    assert a.post(f"/api/admin/users/{uid}/bonus", json={"chars": 2500, "reason": "sorry for the outage"}).status_code == 200
    assert c.get("/api/usage").json()["allowance"] == before + 2500
    assert a.post(f"/api/admin/users/{uid}/bonus", json={"chars": 0, "reason": "x x x"}).status_code == 422
    assert a.get(f"/api/admin/users/{uid}").json()["bonus"][0]["chars"] == 2500


def test_suspend_blocks_sessions_login_and_api_keys(staff, anon, make_invite, set_plan):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    set_plan("creator", email="cust@example.com")
    key = c.post("/api/keys", json={"name": "k"}).json()["key"]
    r = a.post(f"/api/admin/users/{uid}/suspend", json={"suspend": True, "reason": "scam scripts", "notify": True})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert c.get("/api/auth/me").status_code == 401                               # signed out everywhere
    r = c.post("/api/auth/login", json={"email": "cust@example.com", "password": PW})
    assert r.status_code == 403 and "paused" in r.json()["detail"]
    with identity(c):
        assert c.get("/api/usage", headers={"X-API-Key": key}).status_code == 403
    assert a.get("/api/admin/users?status=suspended").json()["total"] == 1
    assert a.post(f"/api/admin/users/{uid}/suspend", json={"suspend": False, "reason": "appeal accepted"}).status_code == 200
    assert c.post("/api/auth/login", json={"email": "cust@example.com", "password": PW}).status_code == 200
    assert a.post(f"/api/admin/users/{a.get('/api/admin/me').json()['user']['id']}/suspend",
                  json={"suspend": True, "reason": "self"}).status_code in (403, 422)


def test_staff_targets_are_owner_only(staff):
    owner, admin, support = staff("owner"), staff("admin"), staff("support")
    sid = support.get("/api/admin/me").json()["user"]["id"]
    oid = owner.get("/api/admin/me").json()["user"]["id"]
    assert admin.post(f"/api/admin/users/{sid}/suspend", json={"suspend": True, "reason": "test"}).status_code == 403
    assert admin.post(f"/api/admin/users/{oid}/sessions/revoke").status_code == 403
    assert owner.post(f"/api/admin/users/{sid}/suspend", json={"suspend": True, "reason": "test test"}).status_code == 200


def test_generation_content_needs_reason_and_is_audited(staff, anon, make_invite):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    gid = c.post("/api/tts?wait=true", json={"text": "Secret script for my reel."}).json()["id"]
    rows = a.get(f"/api/admin/users/{uid}/generations").json()["items"]
    assert rows[0]["id"] == gid and "text_excerpt" not in rows[0] and "Secret" not in str(rows)   # metadata only
    assert a.get(f"/api/admin/generations/{gid}/audio").status_code == 403                     # not revealed yet
    assert a.post(f"/api/admin/generations/{gid}/reveal", json={"reason": "curiosity"}).status_code == 422
    r = a.post(f"/api/admin/generations/{gid}/reveal", json={"reason": "abuse_report", "note": "ticket 12"})
    assert r.status_code == 200 and "Secret script" in r.json()["excerpt"]
    assert a.get(r.json()["audio_url"]).headers["content-type"] == "audio/mpeg"
    e = a.get("/api/admin/audit?action=user.content.reveal").json()["items"][0]
    assert e["target_id"] == gid and "Abuse report: ticket 12" == e["reason"]
    viewer = staff("viewer")
    assert viewer.post(f"/api/admin/generations/{gid}/reveal", json={"reason": "abuse_report"}).status_code == 403


def test_impersonation_is_read_only_time_limited_and_audited(staff, anon, make_invite, app_env):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    c.post("/api/pronunciations", json={"word": "GST", "say_as": "G S T"})
    assert a.post(f"/api/admin/users/{uid}/impersonate", json={"reason": "support ticket: can't see history"}).status_code == 200
    me = a.get("/api/auth/me").json()
    assert me["email"] == "cust@example.com" and me["impersonation"]["by"] == a.email and me["staff"] is False
    assert [x["word"] for x in a.get("/api/pronunciations").json()["items"]] == ["GST"]     # sees the user's data
    for method, path, body in (("POST", "/api/tts", {"text": "hello"}), ("POST", "/api/auth/password",
                               {"current_password": PW, "new_password": "another long one"}),
                               ("POST", "/api/billing/subscribe", {"plan": "pro", "period": "monthly"}),
                               ("POST", "/api/auth/delete-account", {"password": PW, "confirm": "DELETE"}),
                               ("POST", "/api/keys", {"name": "x"})):
        r = a.request(method, path, json=body)
        assert r.status_code == 403 and "Read-only" in r.json()["detail"], path
    assert a.get("/api/admin/me").status_code == 404                     # admin panel closed while viewing as user
    r = a.post("/api/admin/impersonate/stop")
    assert r.status_code == 200 and r.json()["redirect"] == f"/admin/users/{uid}"
    assert a.get("/api/auth/me").json()["email"] == a.email
    actions = [x["action"] for x in a.get("/api/admin/audit?action=impersonate").json()["items"]]
    assert actions == ["impersonate.stop", "impersonate.start"]
    # Expiry: back to the staff member's own view automatically
    a.post(f"/api/admin/users/{uid}/impersonate", json={"reason": "again"})
    from sqlalchemy import update

    from db import utcnow
    from models import UserSession

    async def expire(db):
        await db.execute(update(UserSession).where(UserSession.impersonate_user_id.is_not(None))
                         .values(impersonate_until=utcnow() - timedelta(seconds=1)))
    run_db(app_env, expire)
    assert a.get("/api/auth/me").json()["email"] == a.email


def test_export_and_delete_user(staff, anon, make_invite, clock):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    c.post("/api/tts?wait=true", json={"text": "Export me."})
    stepup(a, clock)
    r = a.get(f"/api/admin/users/{uid}/export")
    data = r.json()
    assert r.status_code == 200 and data["account"]["email"] == "cust@example.com" and data["generations"][0]["text_excerpt"] == "Export me."
    assert data["generations"][0]["audio_mp3"].startswith("https://login.aiwazz.in/api/audio/")
    assert a.post(f"/api/admin/users/{uid}/delete", json={"confirm_email": "wrong@example.com", "reason": "DPDP request"}).status_code == 422
    r = a.post(f"/api/admin/users/{uid}/delete", json={"confirm_email": "cust@example.com", "reason": "DPDP request"})
    assert r.status_code == 200 and r.json()["reference"].startswith("DEL-")
    assert a.get(f"/api/admin/users/{uid}").status_code == 404
    assert c.get("/api/auth/me").status_code == 401
    assert a.get("/api/admin/audit?action=user.delete").json()["items"][0]["target_label"] == "cust@example.com"


def test_password_reset_link_flow(staff, anon, make_invite, app_env, monkeypatch):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    assert a.post(f"/api/admin/users/{uid}/password-reset").status_code == 503     # mail is off
    import secrets

    from auth.security import sha256
    from db import utcnow
    from models import PasswordReset
    token = secrets.token_urlsafe(32)

    async def add(db):
        db.add(PasswordReset(user_id=uid, token_hash=sha256(token), expires_at=utcnow() + timedelta(hours=1)))
    run_db(app_env, add)
    with identity(c, keep_origin=True):
        c.headers["X-CSRF-Token"] = c.get("/api/auth/csrf").json()["csrf_token"]
        assert c.post("/api/auth/reset-password", json={"token": token, "new_password": "brand new password 9"}).status_code == 200
        assert c.post("/api/auth/reset-password", json={"token": token, "new_password": "brand new password 9"}).status_code == 422
        assert c.post("/api/auth/login", json={"email": "cust@example.com", "password": "brand new password 9"}).status_code == 200


def test_notes_tags_sessions_keys_timeline(staff, anon, make_invite, set_plan):
    a = staff("support")
    adm = staff("admin")
    c, uid = _customer(anon, make_invite)
    assert a.post(f"/api/admin/users/{uid}/notes", json={"body": "called about invoice"}).status_code == 403   # support: read only
    assert adm.post(f"/api/admin/users/{uid}/notes", json={"body": "called about invoice"}).status_code == 200
    assert a.get(f"/api/admin/users/{uid}/notes").json()["items"][0]["body"] == "called about invoice"
    assert adm.put(f"/api/admin/users/{uid}/tags", json={"tags": ["Early Access", "vip", "vip"]}).json()["tags"] == ["early-access", "vip"]
    assert adm.get("/api/admin/users?tag=vip").json()["total"] == 1
    set_plan("pro", email="cust@example.com")
    c.post("/api/keys", json={"name": "pipeline"})
    kid = adm.get(f"/api/admin/users/{uid}/keys").json()["items"][0]["id"]
    assert adm.delete(f"/api/admin/users/{uid}/keys/{kid}").status_code == 200
    kinds = {e["kind"] for e in adm.get(f"/api/admin/users/{uid}/timeline").json()["items"]}
    assert {"signup", "login", "staff"} <= kinds
    assert adm.get(f"/api/admin/users/{uid}/sessions").json()["items"]
    assert adm.post(f"/api/admin/users/{uid}/sessions/revoke").json()["sessions"] == 1
    assert c.get("/api/auth/me").status_code == 401


def test_bulk_actions(staff, anon, make_invite, clock):
    a = staff("admin")
    _, u1 = _customer(anon, make_invite, "b1@example.com", "BULK-0001")
    _, u2 = _customer(anon, make_invite, "b2@example.com", "BULK-0002")
    assert a.post("/api/admin/users/bulk", json={"ids": [u1, u2], "action": "tag_add", "tag": "beta"}).json()["affected"] == 2
    r = a.post("/api/admin/users/bulk", json={"ids": [u1, u2], "action": "plan", "plan": "starter", "reason": "promo"})
    assert r.status_code == 403
    stepup(a, clock)
    assert a.post("/api/admin/users/bulk", json={"ids": [u1, u2], "action": "plan", "plan": "starter", "reason": "promo"}).json()["affected"] == 2
    r = a.post("/api/admin/users/bulk", json={"ids": [u1], "action": "email", "subject": "Hi", "message": "News"})
    assert r.json()["affected"] == 1 and r.json()["mail_enabled"] is False


def test_invites_with_plan_and_staff_rules(staff, anon):
    owner, admin = staff("owner"), staff("admin")
    assert admin.post("/api/admin/invites", json={"role": "support"}).status_code == 403          # staff invites: owner only
    until = (date.today() + timedelta(days=90)).isoformat()
    r = admin.post("/api/admin/invites", json={"label": "Riya", "plan": "creator", "plan_until": until})
    assert r.status_code == 200 and r.json()["status"] == "active"
    code = r.json()["code"]
    c = new_client(anon.app, share=anon)
    assert signup(c, email="riya@example.com", password=PW, code=code).status_code == 201
    u = c.get("/api/usage").json()
    assert u["plan"] == "creator" and u["plan_until"].startswith(until)
    assert admin.get("/api/admin/invites?status=used&q=Riya").json()["total"] == 1
    iid = admin.post("/api/admin/invites", json={}).json()["id"]
    assert admin.post(f"/api/admin/invites/{iid}/revoke").json()["status"] == "revoked"
    assert owner.post("/api/admin/invites", json={"role": "finance"}).json()["role"] == "finance"


def test_waitlist_approve_reject_bulk(staff, anon):
    a = staff("admin")
    for e in ("w1@example.com", "w2@example.com", "w3@example.com"):
        assert anon.post("/api/auth/invite-request", json={"email": e, "name": "W", "use_case": "reels"}).status_code == 202
    items = a.get("/api/admin/invite-requests?status=new").json()["items"]
    ids = {i["email"]: i["id"] for i in items}
    r = a.post(f"/api/admin/invite-requests/{ids['w1@example.com']}/approve", json={"plan": "creator"})
    assert r.status_code == 200 and r.json()["email_status"] == "disabled" and r.json()["code"]
    assert a.post(f"/api/admin/invite-requests/{ids['w1@example.com']}/approve", json={}).status_code == 409
    c = new_client(anon.app, share=anon)
    assert signup(c, email="w1@example.com", password=PW, code=r.json()["code"]).status_code == 201
    assert a.post(f"/api/admin/invite-requests/{ids['w2@example.com']}/reject", json={"send_email": True}).json()["status"] == "declined"
    r = a.post("/api/admin/invite-requests/bulk-approve", json={"ids": list(ids.values())})
    assert [x["email"] for x in r.json()["approved"]] == ["w2@example.com", "w3@example.com"] or \
        sorted(x["email"] for x in r.json()["approved"]) == ["w2@example.com", "w3@example.com"]
    assert r.json()["skipped"] == ["w1@example.com"]
    listed = {i["email"]: i for i in a.get("/api/admin/invite-requests").json()["items"]}
    assert listed["w1@example.com"]["registered"] is True
    from tests.conftest import run_db  # noqa: F401
    logs = a.get("/api/admin/audit?action=invite.request").json()["total"]
    assert logs == 4


def test_signup_modes(staff, anon, clock):
    a = staff("owner")
    stepup(a, clock)
    assert a.put("/api/admin/settings/signup", json={"signup_mode": "closed"}).status_code == 200
    c = new_client(anon.app, share=anon)
    r = c.post("/api/auth/signup", json={"email": "x@example.com", "password": PW, "invite_code": "", "accept_terms": True})
    assert r.status_code == 403
    a.put("/api/admin/settings/signup", json={"signup_mode": "open"})
    r = c.post("/api/auth/signup", json={"email": "x@example.com", "password": PW, "accept_terms": True})
    assert r.status_code == 201 and r.json()["role"] == "user"
    a.put("/api/admin/settings/signup", json={"signup_mode": "invite"})
    c2 = new_client(anon.app, share=anon)
    assert c2.post("/api/auth/signup", json={"email": "y@example.com", "password": PW, "accept_terms": True}).status_code == 422


def test_overview_search_notifications(staff, anon, make_invite):
    a = staff("admin")
    c, uid = _customer(anon, make_invite)
    c.post("/api/tts?wait=true", json={"text": "Hello there."})
    anon.post("/api/auth/invite-request", json={"email": "wait@example.com"})
    o = a.get("/api/admin/overview").json()
    k = o["kpis"]
    assert k["signups"]["today"] == 2 and k["generations_today"] == 1 and k["chars_today"] == len("Hello there.")
    assert len(o["charts"]["signups"]) == 30 and o["charts"]["signups"][-1]["value"] == 2
    assert {x["plan"] for x in o["charts"]["plan_mix"]} == {"Free"}
    assert o["lists"]["signups"][0]["email"] == "cust@example.com"
    hits = a.get("/api/admin/search?q=cust").json()["items"]
    assert hits[0]["type"] == "user" and hits[0]["to"] == f"/admin/users/{uid}"
    notes = a.get("/api/admin/notifications").json()["items"]
    assert any(n["id"] == "waitlist" for n in notes)
    v = staff("viewer")
    o = v.get("/api/admin/overview").json()
    assert o["lists"]["signups"] == [] and o["kpis"]["total_users"] >= 3          # viewer: numbers only, no emails

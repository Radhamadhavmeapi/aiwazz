"""A7: email templates/log/suppression, announcements (banners by audience, schedule), changelog, DPDP requests,
consents, deletion log, legal.json editor, settings (general, limits, flags, payments go-live), team & roles."""
import json
from datetime import UTC, datetime, timedelta

from tests.conftest import PW, new_client, run_db, signup, stepup


def test_email_templates_preview_test_send_and_suppression(staff, client, app_env):
    a = staff("admin")
    items = a.get("/api/admin/email/templates").json()["items"]
    keys = {t["key"] for t in items}
    assert {"welcome", "invite", "verify_email", "password_reset", "payment_receipt", "payment_failed", "plan_changed",
            "subscription_cancelled", "account_deleted", "support_reply", "grievance_ack"} <= keys
    bad = a.put("/api/admin/email/templates/welcome", json={"subject": "Hi {{nme}}", "body": "x"})
    assert bad.status_code == 422 and "nme" in bad.json()["detail"]
    assert a.put("/api/admin/email/templates/welcome", json={"subject": "Welcome, {{name}}!", "body": "Hello {{name}}.\n\nGo: {{app_url}}"}).status_code == 200
    pv = a.post("/api/admin/email/preview", json={"key": "welcome", "subject": "Welcome, {{name}}!", "body": "Hello {{name}}. <b>x</b>"}).json()
    assert pv["subject"] == "Welcome, Riya!" and "&lt;b&gt;" in pv["html"] and "AiWazz" in pv["html"]
    r = a.post("/api/admin/email/test-send", json={"key": "welcome"}).json()
    assert r["status"] == "disabled" and r["to"] == a.email
    log = a.get("/api/admin/email/log").json()["items"][0]
    assert log["subject"] == "Welcome, Riya!" and log["status"] == "disabled"
    assert a.delete("/api/admin/email/templates/welcome").status_code == 200
    assert next(t for t in a.get("/api/admin/email/templates").json()["items"] if t["key"] == "welcome")["customized"] is False
    assert a.post("/api/admin/email/suppressions", json={"email": a.email, "reason": "manual"}).status_code == 200
    assert a.post("/api/admin/email/test-send", json={"key": "welcome"}).json()["status"] == "suppressed"
    assert a.delete(f"/api/admin/email/suppressions/{a.email}").status_code == 200


def test_announcements_audience_and_schedule(staff, client, set_plan, anon):
    a = staff("admin")
    a.post("/api/admin/announcements", json={"text": "Paid users: new voices!", "audience": "paid"})
    a.post("/api/admin/announcements", json={"text": "Hello everyone", "audience": "all", "level": "warning"})
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    a.post("/api/admin/announcements", json={"text": "Tomorrow", "audience": "all", "starts_at": future})
    texts = [b["text"] for b in client.get("/api/banners").json()["banners"]]
    assert texts == ["Hello everyone"]
    set_plan("creator")
    assert {b["text"] for b in client.get("/api/banners").json()["banners"]} == {"Hello everyone", "Paid users: new voices!"}
    rows = a.get("/api/admin/announcements").json()["items"]
    assert {r["state"] for r in rows} == {"live", "scheduled"}
    aid = rows[-1]["id"]
    a.put(f"/api/admin/announcements/{aid}", json={"text": "Paid users: new voices!", "audience": "paid", "active": False})
    assert [b["text"] for b in client.get("/api/banners").json()["banners"]] == ["Hello everyone"]


def test_changelog_crud_and_export(staff, monkeypatch, app_env):
    from admin import jobs
    started = []
    monkeypatch.setattr(jobs, "start", lambda sm, name, fn: started.append(name) or True)
    a = staff("admin")
    r = a.post("/api/admin/changelog", json={"title": "Studio voices", "body_md": "**Veer** is here.", "published_on": "2026-11-24",
                                             "tag": "new", "is_published": False})
    assert r.status_code == 200 and "landing_rebuild" not in r.json()
    cid = r.json()["id"]
    r = a.put(f"/api/admin/changelog/{cid}", json={"title": "Studio voices", "body_md": "**Veer** is here.", "published_on": "2026-11-24",
                                                    "tag": "new", "is_published": True})
    assert r.json()["landing_rebuild"] == "started" and started == ["landing-deploy"]
    from admin.announcements import export_changelog

    async def ex(db):
        return await export_changelog(db)
    out = run_db(app_env, ex)
    assert out == [{"id": cid, "title": "Studio voices", "body": "**Veer** is here.", "tag": "new", "date": "2026-11-24"}]


def test_dsr_consents_deletions(staff, client, anon, make_invite):
    a = staff("admin")
    r = a.post("/api/admin/dsr", json={"kind": "access", "email": "me@example.com", "details": "Asked by email"})
    d = r.json()
    assert d["user_id"] and d["status"] == "new" and d["due_at"]
    assert a.get("/api/admin/dsr?status=open").json()["total"] == 1
    assert a.patch(f"/api/admin/dsr/{d['id']}", json={"status": "done", "notes": "Export sent"}).json()["completed_at"]
    c = a.get("/api/admin/compliance/consents?q=me@example.com").json()["items"][0]
    assert c["terms_version"] and c["consent_at"]
    client.post("/api/auth/delete-account", json={"password": "correct horse battery", "confirm": "DELETE"})
    assert a.get("/api/admin/compliance/deletions?q=me@example.com").json()["total"] == 1     # found by email hash
    assert a.get("/api/admin/compliance/policy-history").status_code == 200


def test_legal_editor(staff, clock, monkeypatch, tmp_path):
    from admin import jobs, legal_store
    from billing import gst
    path = tmp_path / "legal.json"
    path.write_text(json.dumps(legal_store.read()))
    monkeypatch.setattr(legal_store, "PATH", path)

    async def no_commit(msg, author):
        return "def5678"
    monkeypatch.setattr(legal_store, "commit", no_commit)
    monkeypatch.setattr(jobs, "start", lambda *a, **k: True)
    saved = json.loads(json.dumps(gst.LEGAL))
    try:
        o = staff("owner")
        data = o.get("/api/admin/legal").json()["data"]
        assert "plans" not in data
        data["supportHours"] = "10:00 to 19:00 IST, Monday to Saturday"
        prev = o.post("/api/admin/legal/preview", json={"data": data}).json()
        assert prev["errors"] == [] and prev["changes"][0]["path"] == "supportHours"
        bad = dict(data, gstin="NOTAGSTIN")
        assert any("gstin" in e for e in o.post("/api/admin/legal/preview", json={"data": bad}).json()["errors"])
        assert o.put("/api/admin/legal", json={"data": data}).status_code == 403
        stepup(o, clock)
        r = o.put("/api/admin/legal", json={"data": data})
        assert r.status_code == 200 and r.json()["commit"] == "def5678"
        stored = json.loads(path.read_text())
        assert stored["supportHours"].startswith("10:00") and stored["plans"] == legal_store.read()["plans"]
        assert staff("support").put("/api/admin/legal", json={"data": data}).status_code == 403
    finally:
        gst.LEGAL.clear()
        gst.LEGAL.update(saved)


def test_settings_limits_flags(staff, client, clock):
    o = staff("owner")
    s = o.get("/api/admin/settings/all").json()
    assert s["limits"]["max_chars"] == 5000 and s["general"]["signup_mode"] == "invite"
    assert {i["name"] for i in s["integrations"]} >= {"Razorpay", "Mail (Postfix on this server)"}
    assert o.put("/api/admin/settings/limits", json={"max_chars": 200, "queue_per_user": 2, "retention_days": 5}).status_code == 200
    r = client.post("/api/tts", json={"text": "x" * 300})
    assert r.status_code == 422
    assert client.get("/api/app-config").json()["max_chars"] == 200
    o.put("/api/admin/settings/limits", json={"max_chars": 5000, "queue_per_user": 3, "retention_days": 7})
    stepup(o, clock)
    o.put("/api/admin/settings/flags", json={"premium_voices": False, "hinglish_default": True, "referrals": False, "open_signup": False})
    assert client.get("/api/app-config").json()["hinglish_default"] is True
    assert o.put("/api/admin/settings/general", json={"product_name": "AiWazz", "support_email": "support@aiwazz.in",
                                                     "signup_mode": "invite"}).status_code == 200


def test_payments_go_live_checklist(staff, clock):
    o = staff("owner")
    p = o.get("/api/admin/settings/all").json()["payments"]
    assert p["mode"] == "OFF" and p["ready_for_live"] is False and len(p["checklist"]) == 5
    stepup(o, clock)
    assert o.post("/api/admin/settings/payments/live", json={"approve": True, "confirm": "nope"}).status_code == 422
    r = o.post("/api/admin/settings/payments/live", json={"approve": True, "confirm": "GO LIVE"})
    assert r.status_code == 200 and r.json()["live_approved"] is True                       # OFF mode: no checklist gate
    a = staff("admin")
    stepup(a, clock)
    assert a.post("/api/admin/settings/payments/live", json={"approve": False, "confirm": ""}).status_code == 403   # owner only


def test_team_roles(staff, anon, clock):
    o = staff("owner")
    a = staff("admin")
    sup = staff("support")
    t = o.get("/api/admin/team").json()
    assert {s["role"] for s in t["staff"]} == {"owner", "admin", "support"} and all(s["mfa"] for s in t["staff"])
    assert a.post("/api/admin/team/invite", json={"email": "new@example.com", "role": "finance"}).status_code == 403
    inv = o.post("/api/admin/team/invite", json={"email": "new@example.com", "role": "finance"}).json()
    assert inv["email_status"] == "disabled" and inv["code"]
    assert o.get("/api/admin/team").json()["invites"][0]["role"] == "finance"
    c = new_client(anon.app, share=anon)
    assert signup(c, email="new@example.com", password=PW, code=inv["code"]).json()["role"] == "finance"
    assert c.get("/api/admin/me").json()["mfa"]["enrolled"] is False                     # 2FA enforced on first visit
    sid = sup.get("/api/admin/me").json()["user"]["id"]
    assert o.put(f"/api/admin/team/{sid}/role", json={"role": "viewer"}).status_code == 403   # step-up
    stepup(o, clock)
    assert o.put(f"/api/admin/team/{sid}/role", json={"role": "viewer"}).json()["role"] == "viewer"
    assert sup.get("/api/admin/audit").headers.get("x-admin-lock") == "verify"             # role change locks their sessions
    assert o.post(f"/api/admin/team/{sid}/active", json={"active": False, "reason": "left the team"}).status_code == 200
    assert sup.get("/api/auth/me").status_code == 401
    aid = a.get("/api/admin/me").json()["user"]["id"]
    assert o.post("/api/admin/team/transfer-ownership", json={"user_id": aid, "confirm_email": "wrong"}).status_code == 422
    assert o.post("/api/admin/team/transfer-ownership", json={"user_id": aid, "confirm_email": a.email}).status_code == 200
    assert a.get("/api/auth/me").json()["role"] == "owner" and o.get("/api/auth/me").json()["role"] == "admin"

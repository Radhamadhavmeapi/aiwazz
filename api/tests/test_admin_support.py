"""A4: support inbox (tickets from contact/invite/grievance/abuse, replies, notes, assignment, grievance timelines,
canned replies) and moderation (rules flag/block at submit, tester, flags actions, blocklist, abuse signals)."""
from datetime import timedelta

from tests.conftest import PW, new_client, run_db, signup

LANDING = "https://aiwazz.in"


def contact(anon, topic="general", email="visitor@example.com", subject="Question", message="Hello there, a question about plans."):
    return anon.post("/api/contact", headers={"Origin": LANDING},
                     json={"name": "Visitor", "email": email, "subject": subject, "message": message, "consent": True, "topic": topic})


def test_contact_and_invite_requests_become_tickets(staff, anon):
    s = staff("support")
    assert contact(anon).status_code == 201
    anon.post("/api/auth/invite-request", json={"email": "wait@example.com", "use_case": "reels for my shop"})
    anon.post("/api/auth/invite-request", json={"email": "wait@example.com", "use_case": "asking again"})
    items = s.get("/api/admin/tickets").json()["items"]
    kinds = sorted(i["kind"] for i in items)
    assert kinds == ["contact", "invite_request"]                      # repeat request = same ticket, new message
    inv = next(i for i in items if i["kind"] == "invite_request")
    d = s.get(f"/api/admin/tickets/{inv['id']}").json()
    assert [m["body"] for m in d["messages"]] == ["reels for my shop", "asking again"]
    assert items[0]["reference"].startswith("AWZ-T-")


def test_reply_threading_notes_assign_and_status(staff, anon, app_env):
    s = staff("support")
    contact(anon)
    tid = s.get("/api/admin/tickets").json()["items"][0]["id"]
    r = s.post(f"/api/admin/tickets/{tid}/reply", json={"body": "Thanks! Here's the answer."})
    assert r.status_code == 200 and r.json()["email_status"] == "disabled" and r.json()["ticket"]["status"] == "waiting"
    s.post(f"/api/admin/tickets/{tid}/reply", json={"body": "Customer seems happy", "note": True})
    s.post(f"/api/admin/tickets/{tid}/reply", json={"body": "Second reply", "status": "resolved"})
    d = s.get(f"/api/admin/tickets/{tid}").json()
    assert [m["direction"] for m in d["messages"]] == ["in", "out", "note", "out"]
    assert d["ticket"]["status"] == "resolved" and d["ticket"]["thread_message_id"].startswith("<")
    from sqlalchemy import select

    from models import EmailLog

    async def logs(db):
        return [(e.template, e.message_id) for e in (await db.execute(select(EmailLog).order_by(EmailLog.id))).scalars()]
    sent = run_db(app_env, logs)
    assert len(sent) == 2 and sent[0][0] == "support_reply" and sent[0][1] == d["ticket"]["thread_message_id"]
    me = s.get("/api/admin/me").json()["user"]["id"]
    r = s.patch(f"/api/admin/tickets/{tid}", json={"assignee_id": me, "priority": "urgent", "status": "open"})
    assert r.json()["assignee_id"] == me and r.json()["priority"] == "urgent"
    assert s.get("/api/admin/tickets?assignee=me").json()["total"] == 1
    assert s.get("/api/admin/tickets/counts").json()["mine"] == 1
    assert staff("viewer").post(f"/api/admin/tickets/{tid}/reply", json={"body": "x"}).status_code == 403


def test_grievance_timelines_and_overdue(staff, anon, app_env):
    s = staff("support")
    contact(anon, topic="grievance", subject="Complaint about a charge", message="I was charged twice, please fix.")
    t = s.get("/api/admin/tickets?kind=grievance").json()["items"][0]
    assert t["priority"] == "high" and t["ack_due_at"] and t["resolve_due_at"] and t["acknowledged_at"] is None
    from sqlalchemy import update

    from db import utcnow
    from models import EmailLog, Ticket

    async def age(db):
        await db.execute(update(Ticket).values(ack_due_at=utcnow() - timedelta(hours=1)))
    run_db(app_env, age)
    assert s.get("/api/admin/tickets?status=overdue").json()["items"][0]["overdue"] == "acknowledgement"
    s.patch(f"/api/admin/tickets/{t['id']}", json={"acknowledged": True})
    assert s.get("/api/admin/tickets?status=overdue").json()["total"] == 0

    async def acks(db):
        from sqlalchemy import select
        return [e.template for e in (await db.execute(select(EmailLog))).scalars()]
    assert run_db(app_env, acks) == ["grievance_ack"]                    # automatic acknowledgement (logged; mail off)


def test_abuse_report_creates_ticket_and_flag(staff, anon):
    m = staff("support")
    contact(anon, topic="abuse", subject="Fake bank call audio", message="Someone used your site to make a fake SBI call.")
    assert m.get("/api/admin/tickets?kind=abuse").json()["total"] == 1
    f = m.get("/api/admin/flags?source=report").json()["items"][0]
    assert f["ticket_id"] and f["severity"] == "high" and f["status"] == "open"


def test_canned_replies(staff):
    s = staff("support")
    r = s.post("/api/admin/canned-replies", json={"title": "Hi", "body": "Hello!"})
    cid = r.json()["id"]
    assert s.put(f"/api/admin/canned-replies/{cid}", json={"title": "Hi 2", "body": "Hello!!"}).json()["title"] == "Hi 2"
    assert [c["title"] for c in s.get("/api/admin/canned-replies").json()["items"]] == ["Hi 2"]
    assert s.delete(f"/api/admin/canned-replies/{cid}").status_code == 200


def test_rules_flag_and_block_scripts(staff, client):
    a = staff("admin")
    r = a.post("/api/admin/moderation/rules", json={"name": "OTP scam", "category": "scam", "kind": "keywords",
                                                     "pattern": "share your OTP, ओटीपी बताएं", "severity": "high", "action": "flag"})
    assert r.status_code == 200
    rid = r.json()["id"]
    assert a.post("/api/admin/moderation/test", json={"text": "Please SHARE   your otp now"}).json()["matches"][0]["term"].lower().startswith("share")
    assert a.post("/api/admin/moderation/test", json={"text": "sharey our otp"}).json()["matches"] == []
    gid = client.post("/api/tts?wait=true", json={"text": "Aap apna ओटीपी बताएं abhi."}).json()["id"]
    f = a.get("/api/admin/flags").json()["items"][0]
    assert f["generation_id"] == gid and f["matched"] == "ओटीपी बताएं" and f["blocked"] is False
    a.put(f"/api/admin/moderation/rules/{rid}", json={"name": "OTP scam", "category": "scam", "kind": "keywords",
                                                       "pattern": "share your OTP", "severity": "high", "action": "block"})
    r = client.post("/api/tts", json={"text": "Please share your OTP with us."})
    assert r.status_code == 422 and "Acceptable Use" in r.json()["detail"]
    assert a.get("/api/admin/flags").json()["items"][0]["blocked"] is True
    assert client.get("/api/usage").json()["used"] == len("Aap apna ओटीपी बताएं abhi.")      # refused job isn't counted
    assert a.post("/api/admin/moderation/rules", json={"name": "bad", "category": "other", "kind": "regex", "pattern": "(",
                                                       "severity": "low", "action": "flag"}).status_code == 422
    assert a.get("/api/admin/moderation/rules").json()["items"][0]["hits_30d"] == 2


def test_flag_actions(staff, client):
    a = staff("admin")
    a.post("/api/admin/moderation/rules", json={"name": "Threat", "category": "threat", "kind": "regex", "pattern": r"kill\s+you",
                                                "severity": "high", "action": "flag"})
    gid = client.post("/api/tts?wait=true", json={"text": "I will kill you."}).json()["id"]
    flags = a.get("/api/admin/flags?status=open").json()["items"]
    fid = flags[0]["id"]
    r = a.post(f"/api/admin/flags/{fid}/action", json={"action": "delete_audio", "note": "threat"})
    assert r.json()["action"] == "audio_deleted" and client.get(f"/api/audio/{gid}?format=mp3").status_code in (404, 410)
    client.post("/api/tts?wait=true", json={"text": "kill you"})
    fid2 = a.get("/api/admin/flags?status=open").json()["items"][0]["id"]
    assert a.post(f"/api/admin/flags/{fid2}/action", json={"action": "warn"}).json()["action"] == "warned"
    client.post("/api/tts?wait=true", json={"text": "kill   you"})
    fid3 = a.get("/api/admin/flags?status=open").json()["items"][0]["id"]
    assert a.post(f"/api/admin/flags/{fid3}/action", json={"action": "suspend", "note": "repeat"}).json()["action"] == "suspended"
    assert client.get("/api/auth/me").status_code == 401
    assert len(a.get("/api/admin/audit?action=moderation.flag").json()["items"]) == 3


def test_blocklist_blocks_signup_and_requests(staff, anon, make_invite):
    a = staff("admin")
    assert a.post("/api/admin/moderation/blocklist", json={"kind": "domain", "value": "@spamco.com", "reason": "bots"}).status_code == 200
    assert a.post("/api/admin/moderation/blocklist", json={"kind": "domain", "value": "spamco.com"}).status_code == 409
    assert a.post("/api/admin/moderation/blocklist", json={"kind": "ip", "value": "not-ip"}).status_code == 422
    make_invite("BLOK-0001")
    c = new_client(anon.app, share=anon)
    r = signup(c, email="x@mail.spamco.com", password=PW, code="BLOK-0001")
    assert r.status_code == 422
    anon.post("/api/auth/invite-request", json={"email": "y@spamco.com"})
    assert a.get("/api/admin/invite-requests?q=spam").json()["total"] == 0
    bid = a.get("/api/admin/moderation/blocklist").json()["items"][0]["id"]
    assert a.delete(f"/api/admin/moderation/blocklist/{bid}").status_code == 200
    assert signup(c, email="x@mail.spamco.com", password=PW, code="BLOK-0001").status_code == 201


def test_abuse_signals_task(staff, anon, make_invite, app_env):
    a = staff("admin")
    for i in range(3):
        make_invite(f"MULT-{i:04d}")
        c = new_client(anon.app, share=anon)
        signup(c, email=f"m{i}@example.com", password=PW, code=f"MULT-{i:04d}")
    import tasks
    from db import make_engine, make_sessionmaker
    from tests.conftest import _run

    async def go():
        eng = make_engine(app_env)
        out = await tasks.abuse_signals(make_sessionmaker(eng), None)
        await eng.dispose()
        return out
    assert "1 new" in _run(go()) or "new flag" in _run(go())
    f = a.get("/api/admin/flags?source=multi_account").json()["items"]
    assert len(f) == 1 and "accounts from" in f[0]["detail"]
    assert "0 new" in _run(go())                                                       # not flagged twice

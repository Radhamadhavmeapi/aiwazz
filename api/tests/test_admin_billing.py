"""A3: subscriptions admin, refunds + credit notes, void, dunning, webhooks log/replay, GST report, plans editor,
coupons, billing-date usage periods, user plan change."""
import hashlib
import hmac
import io
import json
import time
import zipfile
from datetime import timedelta

import pytest

from tests.conftest import PW, new_client, run_db, signup, stepup

WEBHOOK_SECRET = "whsec_test"
KEY_SECRET = "key_secret_test"
NOW = int(time.time())


class FakeRZ:
    def __init__(self):
        self.subs, self.calls, self.refunds, self.plans = {}, [], {}, []
        self.fail_update = False

    async def create_subscription(self, plan_id, total_count, notes, offer_id=""):
        sid = f"sub_{len(self.subs) + 1:04d}"
        self.subs[sid] = {"id": sid, "plan_id": plan_id, "status": "created", "notes": notes}
        self.calls.append(("create", sid, offer_id))
        return self.subs[sid]

    async def get_subscription(self, sid):
        return self.subs[sid]

    async def cancel_subscription(self, sid, at_cycle_end):
        self.calls.append(("cancel", sid, at_cycle_end))
        if not at_cycle_end:
            self.subs[sid]["status"] = "cancelled"
        return self.subs[sid]

    async def update_subscription(self, sid, plan_id, now):
        from billing.razorpay import RazorpayError
        if self.fail_update:
            raise RazorpayError(400, "not supported for UPI")
        self.calls.append(("update", sid, plan_id, now))
        if now:
            self.subs[sid]["plan_id"] = plan_id
        return self.subs[sid]

    async def pause_subscription(self, sid):
        self.subs[sid]["status"] = "paused"
        return self.subs[sid]

    async def resume_subscription(self, sid):
        self.subs[sid]["status"] = "active"
        return self.subs[sid]

    async def refund_payment(self, pid, amount, notes):
        rid = f"rfnd_{len(self.refunds) + 1:03d}"
        self.refunds[rid] = {"id": rid, "payment_id": pid, "amount": amount, "status": "pending"}
        return self.refunds[rid]

    async def create_plan(self, period, amount, name, description, notes):
        pid = f"plan_v{len(self.plans) + 1}"
        self.plans.append((pid, period, amount, notes))
        return {"id": pid}


@pytest.fixture
def rz(app_env, monkeypatch):
    from billing import routes
    from settings import get_settings
    monkeypatch.setenv("AIWAZZ_RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("AIWAZZ_RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("AIWAZZ_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIWAZZ_RAZORPAY_PLAN_IDS", json.dumps({f"{p}_{t}": f"plan_{p}_{t}" for p in ("starter", "creator", "pro")
                                                                for t in ("monthly", "yearly")}))
    get_settings.cache_clear()
    fake = FakeRZ()
    monkeypatch.setattr(routes, "client", lambda: fake)
    return fake


def hook(c, event, payload, event_id=None, secret=WEBHOOK_SECRET):
    raw = json.dumps({"event": event, "payload": payload, "created_at": NOW}).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return c.post("/api/billing/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json",
                                                                "X-Razorpay-Event-Id": event_id or f"evt_{time.time_ns()}"})


def active(sid, plan_id, start=NOW, days=30, status="active"):
    return {"id": sid, "status": status, "plan_id": plan_id, "current_start": start, "current_end": start + days * 86400}


def paying_customer(anon, make_invite, rz, plan="creator", period="monthly", state="27", email="payer@example.com", gstin=""):
    make_invite("PAYR-" + email[:4].upper().ljust(4, "X"))
    c = new_client(anon.app, share=anon)
    assert signup(c, email=email, password=PW, code="PAYR-" + email[:4].upper().ljust(4, "X")).status_code == 201
    c.put("/api/billing/profile", json={"name": "Asha Traders", "state": state, "gstin": gstin, "address": "MG Road" if gstin else ""})
    co = c.post("/api/billing/subscribe", json={"plan": plan, "period": period}).json()
    sid = co["subscription_id"]
    pid = f"plan_{plan}_{period}"
    rz.subs[sid].update(active(sid, pid))
    pay = {"id": f"pay_{sid}", "amount": co["amount_paise"], "status": "captured", "method": "card", "subscription_id": sid}
    assert hook(c, "subscription.charged", {"subscription": {"entity": active(sid, pid)}, "payment": {"entity": pay}}).status_code == 200
    return c, sid, pay


def _ids(a, path, key="items"):
    return a.get(path).json()[key]


def test_refund_partial_then_full_creates_credit_notes(staff, anon, make_invite, rz, clock):
    fin = staff("finance")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    p = _ids(fin, "/api/admin/payments")[0]
    assert p["invoice"]["number"].startswith("AWZ/") and p["invoice"]["cgst_paise"] > 0          # GST split shown
    r = fin.post(f"/api/admin/payments/{p['id']}/refund", json={"amount_paise": 10000, "reason": "partial goodwill"})
    assert r.status_code == 403 and r.headers.get("x-step-up")
    stepup(fin, clock)
    r = fin.post(f"/api/admin/payments/{p['id']}/refund", json={"amount_paise": 10000, "reason": "partial goodwill"})
    assert r.status_code == 200 and r.json()["refund"]["status"] == "pending"
    assert fin.post(f"/api/admin/payments/{p['id']}/refund", json={"amount_paise": pay["amount"], "reason": "too much"}).status_code == 422
    rid = r.json()["refund"]["rzp_refund_id"]
    assert hook(c, "refund.processed", {"refund": {"entity": {"id": rid, "payment_id": pay["id"], "amount": 10000}}}).status_code == 200
    cns = _ids(fin, "/api/admin/credit-notes")
    assert len(cns) == 1 and cns[0]["number"].endswith("/00001") and cns[0]["number"].startswith("AWZ-CN/") and cns[0]["total_paise"] == 10000
    assert cns[0]["cgst_paise"] + cns[0]["sgst_paise"] + cns[0]["taxable_paise"] == 10000
    hook(c, "refund.processed", {"refund": {"entity": {"id": rid}}})                              # replay: nothing new
    assert len(_ids(fin, "/api/admin/credit-notes")) == 1
    r = fin.post(f"/api/admin/payments/{p['id']}/refund", json={"reason": "cancel everything"})   # full = the rest
    rid2 = r.json()["refund"]["rzp_refund_id"]
    assert r.json()["refund"]["amount_paise"] == pay["amount"] - 10000
    hook(c, "refund.processed", {"refund": {"entity": {"id": rid2}}})
    assert _ids(fin, "/api/admin/payments")[0]["status"] == "refunded"
    pdf = fin.get(f"/api/admin/credit-notes/{cns[0]['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert fin.get("/api/admin/audit?action=billing.refund").status_code == 403                   # finance can't read audit
    assert staff("support").post(f"/api/admin/payments/{p['id']}/refund", json={"reason": "xxx"}).status_code == 403


def test_void_invoice_and_regenerate(staff, anon, make_invite, rz, clock):
    a = staff("admin")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    inv = _ids(a, "/api/admin/invoices")[0]
    assert a.post(f"/api/admin/invoices/{inv['id']}/regenerate").status_code == 200
    assert a.get(f"/api/admin/invoices/{inv['id']}/pdf").content[:5] == b"%PDF-"
    stepup(a, clock)
    r = a.post(f"/api/admin/invoices/{inv['id']}/void", json={"reason": "issued in error"})
    assert r.status_code == 200 and r.json()["credit_note"]["total_paise"] == inv["total_paise"] and r.json()["credit_note"]["kind"] == "void"
    assert a.post(f"/api/admin/invoices/{inv['id']}/void", json={"reason": "again"}).status_code == 409
    assert _ids(a, "/api/admin/invoices")[0]["number"] == inv["number"]                          # never renumbered


def test_subscription_admin_actions(staff, anon, make_invite, rz, clock):
    a = staff("admin")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    sub = _ids(a, "/api/admin/subscriptions?status=active")[0]
    assert sub["rzp_subscription_id"] == sid and sub["next_charge_at"]
    stepup(a, clock)
    # Upgrade: now, with Razorpay proration; user gets Pro immediately
    r = a.post(f"/api/admin/subscriptions/{sub['id']}/change-plan", json={"plan": "pro", "period": "monthly", "reason": "asked by phone"})
    assert r.status_code == 200 and r.json()["applies"] == "now" and r.json()["plan"] == "pro"
    assert ("update", sid, "plan_pro_monthly", True) in rz.calls
    assert c.get("/api/auth/me").json()["plan"] == "pro"
    # Downgrade: at period end (pending), user keeps Pro until then
    r = a.post(f"/api/admin/subscriptions/{sub['id']}/change-plan", json={"plan": "starter", "period": "monthly", "reason": "cheaper"})
    assert r.json()["applies"] == "period_end" and r.json()["pending_plan"] == "starter" and r.json()["plan"] == "pro"
    assert ("update", sid, "plan_starter_monthly", False) in rz.calls
    # Renewal on the new plan clears the pending change
    hook(c, "subscription.charged", {"subscription": {"entity": active(sid, "plan_starter_monthly", start=NOW + 30 * 86400)},
                                     "payment": {"entity": {"id": "pay_renew", "amount": 23482, "status": "captured"}}})
    s2 = _ids(a, "/api/admin/subscriptions")[0]
    assert s2["plan"] == "starter" and s2["pending_plan"] is None
    # Pause / resume, cancel now → Free at once
    assert a.post(f"/api/admin/subscriptions/{sub['id']}/pause", json={"pause": True, "reason": "travel"}).json()["status"] == "paused"
    assert a.post(f"/api/admin/subscriptions/{sub['id']}/pause", json={"pause": False, "reason": "back"}).json()["status"] == "active"
    r = a.post(f"/api/admin/subscriptions/{sub['id']}/cancel", json={"at_period_end": False, "reason": "fraud"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert c.get("/api/auth/me").json()["plan"] == "free"
    rz.fail_update = True


def test_user_change_plan_endpoint(anon, make_invite, rz):
    c, sid, pay = paying_customer(anon, make_invite, rz, plan="starter")
    r = c.post("/api/billing/change-plan", json={"plan": "creator", "period": "monthly"})
    assert r.status_code == 200 and r.json()["applies"] == "now"
    r = c.post("/api/billing/change-plan", json={"plan": "creator", "period": "monthly"})
    assert r.status_code == 422
    rz.fail_update = True
    r = c.post("/api/billing/change-plan", json={"plan": "pro", "period": "monthly"})
    assert r.status_code == 502 and "UPI" in r.json()["detail"]


def test_webhook_log_rejects_failures_and_replay(staff, anon, make_invite, rz, monkeypatch):
    a = staff("admin")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    assert hook(c, "subscription.charged", {}, secret="wrong").status_code == 400
    rows = _ids(a, "/api/admin/webhooks")
    assert {r["status"] for r in rows} >= {"processed", "rejected"}
    bad = next(r for r in rows if r["status"] == "rejected")
    assert bad["signature_ok"] is False and a.post(f"/api/admin/webhooks/{bad['id']}/replay").status_code == 409
    # A processing error is logged as failed; Razorpay's retry (same event id) processes it again
    from billing import service
    real = service.handle_event
    calls = {"n": 0}

    async def flaky(db, event, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database hiccup")
        return await real(db, event, payload)
    monkeypatch.setattr(service, "handle_event", flaky)
    p2 = {"id": "pay_retry", "amount": pay["amount"], "status": "captured", "subscription_id": sid}
    body = {"subscription": {"entity": active(sid, "plan_creator_monthly", start=NOW + 30 * 86400)}, "payment": {"entity": p2}}
    assert hook(c, "subscription.charged", body, event_id="evt_flaky").status_code == 500
    assert a.get("/api/admin/webhooks/evt_flaky").json()["status"] == "failed"
    assert hook(c, "subscription.charged", body, event_id="evt_flaky").status_code == 200
    assert a.get("/api/admin/webhooks/evt_flaky").json()["status"] == "processed"
    n_inv = len(_ids(a, "/api/admin/invoices"))
    r = a.post("/api/admin/webhooks/evt_flaky/replay")                                  # idempotent replay
    assert r.status_code == 200 and r.json()["replays"] >= 1
    assert len(_ids(a, "/api/admin/invoices")) == n_inv == 2


def test_dunning_flow(staff, anon, make_invite, rz, app_env):
    a = staff("admin")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    fail = {"id": "pay_fail1", "amount": pay["amount"], "status": "failed", "method": "card", "subscription_id": sid,
            "error_description": "Card declined"}
    hook(c, "payment.failed", {"payment": {"entity": fail}})
    hook(c, "subscription.pending", {"subscription": {"entity": active(sid, "plan_creator_monthly", status="pending")}})
    case = _ids(a, "/api/admin/dunning")[0]
    assert case["status"] == "open" and case["failures"] == 2 and case["last_error"].startswith("Subscription")
    assert _ids(a, "/api/admin/payments?status=failed")[0]["error"] == "Card declined"
    import asyncio  # noqa: F401
    from sqlalchemy import update

    from billing import dunning
    from db import utcnow
    from models import DunningCase, EmailLog

    async def run(db):
        return await dunning.run(db)
    assert "1 emails" in run_db(app_env, run)
    assert "0 emails" in run_db(app_env, run)                                            # day 0 sent once

    async def age(db, days):
        await db.execute(update(DunningCase).values(started_at=utcnow() - timedelta(days=days)))

    run_db(app_env, lambda db: age(db, 3))
    assert "1 emails" in run_db(app_env, run)

    async def logs(db):
        from sqlalchemy import select
        return [e.template for e in (await db.execute(select(EmailLog).order_by(EmailLog.id))).scalars()]
    assert logs and run_db(app_env, logs)[-2:] == ["payment_failed", "dunning_reminder"]

    async def past_grace(db):
        await db.execute(update(DunningCase).values(grace_until=utcnow() - timedelta(minutes=1)))
    run_db(app_env, past_grace)
    assert "1 downgraded" in run_db(app_env, run)
    assert c.get("/api/auth/me").json()["plan"] == "free"
    assert _ids(a, "/api/admin/dunning")[0]["status"] == "downgraded"


def test_dunning_resolved_by_successful_charge(staff, anon, make_invite, rz):
    a = staff("admin")
    c, sid, pay = paying_customer(anon, make_invite, rz)
    hook(c, "payment.failed", {"payment": {"entity": {"id": "pay_f", "amount": 1, "status": "failed", "subscription_id": sid}}})
    hook(c, "subscription.charged", {"subscription": {"entity": active(sid, "plan_creator_monthly", start=NOW + 30 * 86400)},
                                     "payment": {"entity": {"id": "pay_ok2", "amount": pay["amount"], "status": "captured"}}})
    assert _ids(a, "/api/admin/dunning")[0]["status"] == "resolved"


def test_gst_report(staff, anon, make_invite, rz, clock):
    a = staff("finance")
    paying_customer(anon, make_invite, rz, state="27", email="mh@example.com")                    # B2C intra-state
    paying_customer(anon, make_invite, rz, state="29", email="ka@example.com", gstin="")          # B2C inter-state
    paying_customer(anon, make_invite, rz, state="27", email="b2b@example.com", gstin="27ABJFR6148J1ZO")
    from billing.gst import IST
    from db import utcnow
    month = f"{utcnow() + IST:%Y-%m}"
    rep = a.get(f"/api/admin/gst/report?month={month}").json()
    s = rep["summary"]
    assert (s["invoices"], s["b2b"], s["b2c"]) == (3, 1, 2)
    g = s["gross"]
    assert round(g["taxable"] + g["cgst"] + g["sgst"] + g["igst"], 2) == g["total"]
    assert g["igst"] > 0 and g["cgst"] == g["sgst"] > 0
    assert {r["place_of_supply"] for r in rep["sheets"]["b2c_state_wise"]} == {"27-Maharashtra", "29-Karnataka"}
    assert rep["sheets"]["b2b"][0]["buyer_gstin"] == "27ABJFR6148J1ZO" and rep["sheets"]["hsn_sac_summary"][0]["sac"] == "998439"
    assert a.get(f"/api/admin/gst/report?month={month}&format=csv").status_code == 403           # step-up first
    stepup(a, clock)
    csv = a.get(f"/api/admin/gst/report?month={month}&format=csv&sheet=invoice_register")
    assert csv.status_code == 200 and csv.text.count("AWZ/") == 3
    x = a.get(f"/api/admin/gst/report?month={month}&format=xlsx")
    names = zipfile.ZipFile(io.BytesIO(x.content)).namelist()
    assert x.status_code == 200 and any("sheet" in n for n in names)


def test_plans_editor_preview_apply_and_versions(staff, rz, clock, monkeypatch, tmp_path):
    from admin import jobs, legal_store
    from billing import gst
    import usage
    src = legal_store.read()
    path = tmp_path / "legal.json"
    path.write_text(json.dumps(src))
    monkeypatch.setattr(legal_store, "PATH", path)

    async def no_commit(msg, author):
        return "abc1234"
    monkeypatch.setattr(legal_store, "commit", no_commit)
    monkeypatch.setattr(jobs, "start", lambda *a, **k: True)
    saved_legal, saved_plans = json.loads(json.dumps(gst.LEGAL)), dict(usage.PLANS)
    try:
        a = staff("owner")
        plans = a.get("/api/admin/plans").json()["plans"]
        plans[2]["priceMonthly"] = 599
        plans[2]["features"] = plans[2]["features"] + ["New: priority voice"]
        plans[1]["visibility"] = "hidden"
        body = {"plans": plans, "yearlyDiscountPercent": 20}
        prev = a.post("/api/admin/plans/preview", json=body).json()
        assert prev["errors"] == [] and {c["plan"] for c in prev["price_changes"]} == {"creator"}
        assert any(c["path"] == "plans[creator].priceMonthly" for c in prev["changes"])
        bad = json.loads(json.dumps(body))
        bad["plans"][0]["priceMonthly"] = 10
        bad["plans"][3]["popular"] = bad["plans"][2]["popular"] = True
        errs = a.post("/api/admin/plans/preview", json=bad).json()["errors"]
        assert any("free.priceMonthly" in e for e in errs) and any("popular" in e for e in errs)
        assert a.put("/api/admin/plans", json=body).status_code == 403                             # step-up
        stepup(a, clock)
        r = a.put("/api/admin/plans", json=body)
        assert r.status_code == 200, r.text
        assert {(v["plan"], v["period"]) for v in r.json()["new_versions"]} == {("creator", "monthly"), ("creator", "yearly")}
        assert rz.plans[0][2] == 59900 * 118 // 100                                                  # new Razorpay plan, GST incl.
        assert json.loads(path.read_text())["plans"][2]["priceMonthly"] == 599
        assert gst.plan_prices()["creator"]["monthly"] == 599                                       # reloaded in process
        v = a.get("/api/admin/plans").json()["versions"]
        assert [x["active"] for x in v if x["plan"] == "creator"] == [True, True]
        assert a.put("/api/admin/plans", json=body).status_code == 422                              # nothing changed
        assert staff("finance").put("/api/admin/plans", json=body).status_code == 403
    finally:
        gst.LEGAL.clear()
        gst.LEGAL.update(saved_legal)
        usage.PLANS.clear()
        usage.PLANS.update(saved_plans)


def test_coupons(staff, anon, make_invite, rz):
    a = staff("finance")
    r = a.post("/api/admin/coupons", json={"code": "launch20", "kind": "percent", "value": 20, "plans": ["creator"],
                                           "max_redemptions": 1, "rzp_offer_id": "offer_ABC123"})
    assert r.status_code == 200 and r.json()["code"] == "LAUNCH20" and r.json()["state"] == "active"
    assert a.post("/api/admin/coupons", json={"code": "LAUNCH20", "kind": "percent", "value": 5}).status_code == 409
    assert a.post("/api/admin/coupons", json={"code": "BAD", "kind": "percent", "value": 150}).status_code == 422
    make_invite("CPN1-AAAA")
    c = new_client(anon.app, share=anon)
    signup(c, email="cp@example.com", password=PW, code="CPN1-AAAA")
    c.put("/api/billing/profile", json={"name": "C P", "state": "27"})
    assert c.post("/api/billing/subscribe", json={"plan": "pro", "period": "monthly", "coupon": "launch20"}).status_code == 422
    assert c.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly", "coupon": "nope"}).status_code == 422
    r = c.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly", "coupon": "launch20"})
    assert r.status_code == 200 and rz.calls[-1] == ("create", r.json()["subscription_id"], "offer_ABC123")
    cid = _ids(a, "/api/admin/coupons")[0]["id"]
    red = _ids(a, f"/api/admin/coupons/{cid}/redemptions")
    assert red[0]["email"] == "cp@example.com" and red[0]["status"] == "pending"
    assert _ids(a, "/api/admin/coupons")[0]["state"] == "used up"
    r = a.put(f"/api/admin/coupons/{cid}", json={"code": "LAUNCH20", "kind": "percent", "value": 20, "active": False})
    assert r.json()["state"] == "inactive"
    s = a.put("/api/admin/settings/referrals", json={"enabled": False, "reward_chars_referrer": 1, "reward_chars_referred": 2})
    assert s.status_code == 200 and a.get("/api/admin/settings/referrals").json()["enabled"] is False


def test_usage_resets_on_billing_date(anon, make_invite, rz):
    c, sid, pay = paying_customer(anon, make_invite, rz)
    start = NOW - 40 * 86400
    hook(c, "subscription.charged", {"subscription": {"entity": active(sid, "plan_creator_monthly", start=NOW - 10 * 86400)},
                                     "payment": {"entity": {"id": "pay_x", "amount": pay["amount"], "status": "captured"}}})
    u = c.get("/api/usage").json()
    from datetime import UTC, datetime
    ps = datetime.fromisoformat(u["period_start"].rstrip("Z"))
    assert abs((ps - datetime.fromtimestamp(NOW - 10 * 86400, UTC).replace(tzinfo=None)).total_seconds()) < 2
    assert start  # anchored on the billing date, not the 1st of the month


def test_anchored_bounds_month_ends():
    from datetime import UTC, datetime

    from usage import anchored_bounds
    s, e = anchored_bounds(datetime(2026, 1, 31, 10), datetime(2026, 3, 1, 9))
    assert (s, e) == (datetime(2026, 2, 28, 10), datetime(2026, 3, 31, 10))
    s, e = anchored_bounds(datetime(2026, 1, 15), datetime(2026, 1, 20))
    assert (s, e) == (datetime(2026, 1, 15), datetime(2026, 2, 15))

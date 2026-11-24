"""Billing: GST maths, GSTIN check, checkout flow, webhook (signature, idempotency, invoice), cancel, account deletion."""
import hashlib
import hmac
import json
import time

import pytest

from billing.gst import charge_paise, financial_year, gstin_problem, plan_prices, rupees, split_tax

WEBHOOK_SECRET = "whsec_test"
KEY_SECRET = "key_secret_test"
NOW = int(time.time())


# ── pure functions ──
def test_prices_and_gst():
    p = plan_prices()
    assert p["starter"]["yearly"] == 12 * p["starter"]["yearly_per_month"] == 1908
    assert charge_paise("starter", "monthly") == (19900, 23482)
    assert charge_paise("creator", "yearly") == (478800, 564984)
    intra, inter = split_tax(23482, "27"), split_tax(23482, "29")
    assert (intra.taxable, intra.cgst, intra.sgst, intra.igst) == (19900, 1791, 1791, 0)
    assert (inter.taxable, inter.igst, inter.cgst) == (19900, 3582, 0)
    assert intra.taxable + intra.cgst + intra.sgst == 23482
    assert rupees(564984) == "₹5,649.84" and rupees(12345678) == "₹1,23,456.78"


def test_financial_year_and_gstin():
    from datetime import datetime
    assert financial_year(datetime(2026, 3, 31, 18, 29)) == "2025-26"   # 23:59 IST on 31 Mar
    assert financial_year(datetime(2026, 3, 31, 18, 31)) == "2026-27"   # 00:01 IST on 1 Apr
    assert gstin_problem("27ABJFR6148J1ZO", "27") is None                # the company's own GSTIN
    assert "typo" in gstin_problem("27ABJFR6148J1ZP", "27")
    assert "Maharashtra" in gstin_problem("27ABJFR6148J1ZO", "29")
    assert "doesn't look right" in gstin_problem("27ABJ", "27")


# ── API with a fake Razorpay ──
class FakeRazorpay:
    def __init__(self):
        self.subs, self.calls = {}, []

    async def create_subscription(self, plan_id, total_count, notes):
        sid = f"sub_{len(self.subs) + 1:04d}"
        self.subs[sid] = {"id": sid, "plan_id": plan_id, "status": "created", "notes": notes}
        self.calls.append(("create", sid))
        return self.subs[sid]

    async def get_subscription(self, sid):
        return self.subs[sid]

    async def cancel_subscription(self, sid, at_cycle_end):
        self.calls.append(("cancel", sid, at_cycle_end))
        s = self.subs[sid]
        if not at_cycle_end:
            s["status"] = "cancelled"
        return s


@pytest.fixture
def billing(client, monkeypatch):
    from billing import routes
    from settings import get_settings
    monkeypatch.setenv("AIWAZZ_RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("AIWAZZ_RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("AIWAZZ_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIWAZZ_RAZORPAY_PLAN_IDS", json.dumps({f"{p}_{t}": f"plan_{p}_{t}" for p in ("starter", "creator", "pro")
                                                                for t in ("monthly", "yearly")}))
    get_settings.cache_clear()
    fake = FakeRazorpay()
    monkeypatch.setattr(routes, "client", lambda: fake)
    return fake


def _profile(c, state="27", gstin=""):
    return c.put("/api/billing/profile", json={"name": "Asha Traders", "state": state, "gstin": gstin,
                                               "address": "12 MG Road, Pune" if gstin else ""})


def _hook(c, event, sub, payment=None, event_id=None):
    payload = {"subscription": {"entity": sub}}
    if payment:
        payload["payment"] = {"entity": payment}
    raw = json.dumps({"event": event, "payload": payload, "created_at": NOW}).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return c.post("/api/billing/webhook", content=raw, headers={"X-Razorpay-Signature": sig,
                  "X-Razorpay-Event-Id": event_id or f"evt_{event}_{payment and payment['id']}", "Content-Type": "application/json"})


def _active(sid, start=NOW, days=30):
    return {"id": sid, "status": "active", "current_start": start, "current_end": start + days * 86400}


def test_overview_disabled_without_keys(client):
    b = client.get("/api/billing").json()
    assert b["enabled"] is False and len(b["plans"]) == 3 and b["subscription"] is None
    assert client.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly"}).status_code == 503


def test_profile_validation(billing, client):
    assert _profile(client, state="99").status_code == 422
    assert "typo" in _profile(client, gstin="27ABJFR6148J1ZP").json()["detail"]
    assert _profile(client, gstin="27ABJFR6148J1ZO").status_code == 200
    assert client.get("/api/billing").json()["profile"]["gstin"] == "27ABJFR6148J1ZO"


def test_full_subscription_flow(billing, client):
    r = client.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly"})
    assert r.status_code == 422 and "billing details" in r.json()["detail"]
    _profile(client, state="29")
    r = client.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly"})
    assert r.status_code == 200, r.text
    co = r.json()
    assert co["key_id"] == "rzp_test_abc" and co["amount_paise"] == 49900 * 118 // 100 and co["subscription_id"] == "sub_0001"

    # Forged checkout signature is rejected; a correct one activates (state read from Razorpay, not the browser)
    bad = {"razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_0001", "razorpay_signature": "x"}
    assert client.post("/api/billing/verify", json=bad).status_code == 400
    billing.subs["sub_0001"].update(_active("sub_0001"))
    sig = hmac.new(KEY_SECRET.encode(), b"pay_1|sub_0001", hashlib.sha256).hexdigest()
    r = client.post("/api/billing/verify", json=bad | {"razorpay_signature": sig})
    assert r.status_code == 200 and r.json()["subscription"]["status"] == "active"
    me = client.get("/api/auth/me").json()
    assert me["plan"] == "creator" and me["api_access"] is True

    # A second subscription while one is live is refused
    assert client.post("/api/billing/subscribe", json={"plan": "pro", "period": "monthly"}).status_code == 409

    # Webhook: bad signature, then the charge → invoice (IGST, other state), replay is ignored
    raw = b'{"event":"subscription.charged"}'
    assert client.post("/api/billing/webhook", content=raw, headers={"X-Razorpay-Signature": "nope"}).status_code == 400
    pay = {"id": "pay_1", "amount": co["amount_paise"], "status": "captured", "method": "upi", "subscription_id": "sub_0001"}
    assert _hook(client, "subscription.charged", _active("sub_0001"), pay).status_code == 200
    assert _hook(client, "subscription.charged", _active("sub_0001"), pay).json().get("duplicate") is True
    assert _hook(client, "subscription.charged", _active("sub_0001"), pay, event_id="evt_other").status_code == 200  # same payment
    inv = client.get("/api/billing").json()["invoices"]
    assert len(inv) == 1 and inv[0]["number"].startswith("AWZ/") and inv[0]["number"].endswith("/00001")
    pdf = client.get(f"/api/billing/invoices/{inv[0]['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

    # Renewal → second consecutive invoice number, plan extended
    pay2 = pay | {"id": "pay_2"}
    _hook(client, "subscription.charged", _active("sub_0001", start=NOW + 30 * 86400), pay2)
    inv = client.get("/api/billing").json()["invoices"]
    assert [i["number"][-5:] for i in inv] == ["00002", "00001"]

    # Cancel at period end: still Creator until then
    r = client.post("/api/billing/cancel")
    assert r.status_code == 200 and r.json()["subscription"]["cancel_at_period_end"] is True
    assert ("cancel", "sub_0001", True) in billing.calls
    assert client.get("/api/auth/me").json()["plan"] == "creator"


def test_invoice_tax_split_same_state(billing, client, app_env):
    _profile(client, state="27")
    client.post("/api/billing/subscribe", json={"plan": "starter", "period": "yearly"})
    pay = {"id": "pay_9", "amount": 225144, "status": "captured", "subscription_id": "sub_0001"}
    _hook(client, "subscription.charged", _active("sub_0001", days=365), pay)
    from tests.conftest import _run

    async def get():
        from sqlalchemy import select
        from db import make_engine, make_sessionmaker
        from models import Invoice
        eng = make_engine(app_env)
        async with make_sessionmaker(eng)() as db:
            i = (await db.execute(select(Invoice))).scalar_one()
        await eng.dispose()
        return i
    i = _run(get())
    assert (i.taxable_paise, i.cgst_paise, i.sgst_paise, i.igst_paise, i.total_paise) == (190800, 17172, 17172, 0, 225144)


def test_account_deletion_cancels_and_keeps_invoice(billing, client, app_env):
    _profile(client)
    client.post("/api/billing/subscribe", json={"plan": "creator", "period": "monthly"})
    _hook(client, "subscription.charged", _active("sub_0001"), {"id": "pay_5", "amount": 58882, "status": "captured"})
    r = client.post("/api/auth/delete-account", json={"password": "correct horse battery", "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert ("cancel", "sub_0001", False) in billing.calls
    from tests.conftest import _run

    async def count():
        from sqlalchemy import func, select
        from db import make_engine, make_sessionmaker
        from models import Invoice
        eng = make_engine(app_env)
        async with make_sessionmaker(eng)() as db:
            n = (await db.execute(select(func.count()).select_from(Invoice).where(Invoice.user_id.is_(None)))).scalar_one()
        await eng.dispose()
        return n
    assert _run(count()) == 1


def test_api_keys_cannot_use_billing(billing, client, set_plan):
    set_plan("creator")
    key = client.post("/api/keys", json={"name": "k"}).json()["key"]
    from tests.conftest import identity
    with identity(client) as bare:
        assert bare.get("/api/billing", headers={"X-API-Key": key}).status_code == 403

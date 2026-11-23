from datetime import datetime

from usage import period_bounds


def test_usage_and_402(client, set_plan):
    u = client.get("/api/usage").json()
    assert u["plan"] == "free" and u["allowance"] == 5000 and u["used"] == 0 and u["api_access"] is False
    text = "A" * 30 + "."
    assert client.post("/api/tts?wait=true", json={"text": text, "voice": "af_heart"}).status_code == 200
    u = client.get("/api/usage").json()
    assert u["used"] == len(text) and u["remaining"] == 5000 - len(text)
    r = client.post("/api/tts", json={"text": "x" * 4990, "voice": "af_heart"})
    assert r.status_code == 402 and "Not enough characters" in r.json()["detail"]
    set_plan("starter")
    assert client.get("/api/usage").json()["allowance"] == 50000
    assert client.post("/api/tts", json={"text": "x" * 4990, "voice": "af_heart"}).status_code in (200, 202)


def test_failed_jobs_are_not_charged(client):
    jm = client.app.state.jobs
    orig = jm.engine.synthesize
    jm.engine.synthesize = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        r = client.post("/api/tts?wait=true", json={"text": "This one fails.", "voice": "af_heart"})
        assert r.status_code == 422
    finally:
        jm.engine.synthesize = orig
    assert client.get("/api/usage").json()["used"] == 0


def test_admin_unlimited(anon, make_invite):
    from tests.conftest import signup
    make_invite("ADMN-UNLM", role="admin")
    signup(anon, code="ADMN-UNLM")
    u = anon.get("/api/usage").json()
    assert u["unlimited"] is True and u["allowance"] is None and u["api_access"] is True


def test_delete_history_item(client):
    r = client.post("/api/tts?wait=true", json={"text": "Remove me.", "voice": "af_heart"}).json()
    files = list(client.app.state.jobs.s.audio_dir.glob(f"{r['id']}.*"))
    assert files and client.delete(f"/api/history/{r['id']}").status_code == 200
    assert not any(f.exists() for f in files) and client.get("/api/history").json()["items"] == []
    assert client.delete(f"/api/history/{r['id']}").status_code == 404


def test_period_is_ist_month():
    start, end = period_bounds(datetime(2026, 11, 30, 19, 0))   # 1 Dec 00:30 IST
    assert start == datetime(2026, 11, 30, 18, 30) and end == datetime(2026, 12, 31, 18, 30)

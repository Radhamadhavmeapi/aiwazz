"""A5: voices & styles overrides, samples, API keys & usage (counts, rate overrides, endpoint stats, OpenAPI),
queue & jobs (pause, cancel, retry, maintenance banner)."""

from tests.conftest import identity, stepup


def test_voice_overrides_apply_to_catalogue_and_submit(staff, client, set_plan):
    a = staff("admin")
    voices = a.get("/api/admin/voices").json()["voices"]
    assert len(voices) == 14 and voices[0]["tone"]
    body = {"enabled": False, "display_name": "", "description": "", "tags": [], "sort_order": 0, "is_new": False, "min_plan": "free"}
    assert a.put("/api/admin/voices/hf_beta", json=body).status_code == 200
    assert "hf_beta" not in [v["id"] for v in client.get("/api/voices").json()["voices"]]
    r = client.post("/api/tts", json={"text": "Hello", "voice": "hf_beta"})
    assert r.status_code == 422 and "isn't available" in r.json()["detail"]
    a.put("/api/admin/voices/hf_alpha", json=body | {"enabled": True, "display_name": "Asha", "description": "Warm", "tags": ["female", "hindi"],
                                                     "is_new": True, "min_plan": "pro", "sort_order": 99})
    v = next(x for x in client.get("/api/voices").json()["voices"] if x["id"] == "hf_alpha")
    assert v["name"] == "Asha" and v["tone"] == "Warm" and v["is_new"] and v["available"] is False and v["min_plan"] == "pro"
    assert client.get("/api/voices").json()["voices"][-1]["id"] == "hf_alpha"           # sort order applied
    assert client.post("/api/tts", json={"text": "Hello", "voice": "hf_alpha"}).status_code == 403
    set_plan("pro")
    assert client.post("/api/tts?wait=true", json={"text": "Hello", "voice": "hf_alpha"}).status_code == 200
    assert staff("support").put("/api/admin/voices/hf_alpha", json=body).status_code == 403


def test_style_overrides(staff, client):
    a = staff("admin")
    a.put("/api/admin/styles/calm-narrator", json={"enabled": False, "display_name": "", "description": "", "sort_order": 1})
    a.put("/api/admin/styles/energetic-reel", json={"enabled": True, "display_name": "Reel energy", "description": "Fast", "sort_order": 0})
    st = client.get("/api/styles").json()["styles"]
    assert "calm-narrator" not in [s["id"] for s in st] and st[0]["name"] == "Reel energy"
    assert client.post("/api/tts", json={"text": "Hello", "style": "calm-narrator"}).status_code == 422


def test_regenerate_sample(staff, monkeypatch, tmp_path):
    from admin.routes import product
    (tmp_path / "landing" / "samples").mkdir(parents=True)
    monkeypatch.setattr(product, "ROOT", tmp_path)
    monkeypatch.setattr(product.bg, "start", lambda *a, **k: True)
    a = staff("admin")
    r = a.post("/api/admin/voices/am_puck/sample")
    assert r.status_code == 200 and (tmp_path / "landing" / "samples" / "am_puck.mp3").stat().st_size > 500
    assert a.post("/api/admin/voices/nope/sample").status_code == 404


def test_studio_publish_is_owner_only(staff, clock):
    a = staff("admin")
    stepup(a, clock)
    assert a.post("/api/admin/voices/x/publish", json={"public": True, "reason": "launch"}).status_code == 403
    o = staff("owner")
    stepup(o, clock)
    assert o.post("/api/admin/voices/unknown/publish", json={"public": True, "reason": "launch"}).status_code == 404


def test_api_keys_counts_overrides_and_stats(staff, client, set_plan):
    a = staff("admin")
    set_plan("creator")
    k = client.post("/api/keys", json={"name": "pipeline"}).json()
    with identity(client) as bare:
        for _ in range(3):
            assert bare.get("/api/usage", headers={"X-API-Key": k["key"]}).status_code == 200
    row = a.get("/api/admin/api-keys?q=pipeline").json()["items"][0]
    assert row["requests_24h"] == 3 and row["requests_30d"] == 3 and row["email"] == "me@example.com"
    assert a.post("/api/admin/api/rate-overrides", json={"scope": "key", "target_id": row["id"], "rpm": 4, "note": "test"}).status_code == 200
    with identity(client) as bare:
        codes = [bare.get("/api/usage", headers={"X-API-Key": k["key"]}).status_code for _ in range(2)]
    assert codes == [200, 429]
    u = a.get("/api/admin/api/usage").json()
    assert any(e["endpoint"] == "GET /api/usage" and e["4xx"] >= 1 for e in u["endpoints"])
    assert u["overrides"][0]["rpm"] == 4 and u["default_rpm"] == 60
    a.delete(f"/api/admin/api/rate-overrides/{u['overrides'][0]['id']}")
    spec = a.get("/api/admin/api/openapi").json()
    assert "/api/tts" in spec["paths"] and not any(p.startswith("/api/admin") for p in spec["paths"])
    assert a.post(f"/api/admin/api-keys/{row['id']}/revoke").status_code == 200
    with identity(client) as bare:
        assert bare.get("/api/usage", headers={"X-API-Key": k["key"]}).status_code == 401


def test_queue_pause_cancel_and_maintenance(staff, client, clock, anon):
    a = staff("owner")
    r = a.put("/api/admin/queue/ops", json={"queue_paused": True, "maintenance": False, "message": ""})
    assert r.status_code == 403 and r.headers.get("x-step-up")
    stepup(a, clock)
    a.put("/api/admin/queue/ops", json={"queue_paused": True, "maintenance": False, "message": ""})
    assert client.get("/api/banners").json()["banners"][0]["id"] == "paused"
    j1 = client.post("/api/tts", json={"text": "First one."}).json()
    j2 = client.post("/api/tts", json={"text": "Second one."}).json()
    q = a.get("/api/admin/queue").json()
    assert q["paused"] and {w["id"] for w in q["waiting"]} >= {j2["id"]}
    assert a.post(f"/api/admin/queue/{j2['id']}/cancel").status_code == 200
    assert client.get(f"/api/tts/jobs/{j2['id']}").json()["status"] == "error"
    assert client.get("/api/usage").json()["reserved"] == len("First one.")              # cancelled job no longer reserved
    a.put("/api/admin/queue/ops", json={"queue_paused": False, "maintenance": True, "message": "Back at 10:30"})
    import time
    for _ in range(100):
        if client.get(f"/api/tts/jobs/{j1['id']}").json()["status"] == "done":
            break
        time.sleep(0.05)
    assert client.get(f"/api/tts/jobs/{j1['id']}").json()["status"] == "done"
    r = client.post("/api/tts", json={"text": "During maintenance"})
    assert r.status_code == 503 and r.json()["detail"] == "Back at 10:30"
    assert anon.get("/api/banners").json()["banners"][0]["text"] == "Back at 10:30"
    a.put("/api/admin/queue/ops", json={"queue_paused": False, "maintenance": False, "message": ""})
    assert client.get("/api/banners").json()["banners"] == []
    assert staff("viewer").get("/api/admin/queue").status_code == 200


def test_retry_failed_job(staff, client, monkeypatch):
    a = staff("admin")
    jm = client.app.state.jobs
    real = jm.engine.synthesize
    calls = {"n": 0}

    def flaky(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(*args, **kw)
    monkeypatch.setattr(jm.engine, "synthesize", flaky)
    gid = client.post("/api/tts?wait=true", json={"text": "Retry me."}).json()["id"]
    f = a.get("/api/admin/queue/failures").json()["items"][0]
    assert f["id"] == gid and f["retryable"] is True
    r = a.post(f"/api/admin/queue/{gid}/retry")
    assert r.status_code == 200
    import time
    for _ in range(100):
        if client.get(f"/api/tts/jobs/{r.json()['id']}").json()["status"] == "done":
            break
        time.sleep(0.05)
    assert client.get(f"/api/tts/jobs/{r.json()['id']}").json()["status"] == "done"
    assert a.post(f"/api/admin/queue/{r.json()['id']}/retry").status_code == 409

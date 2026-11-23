import soundfile as sf


def test_health_and_voices(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    voices = client.get("/api/voices").json()["voices"]
    assert {"hf_alpha", "hm_omega", "af_heart", "bf_emma"} <= {v["id"] for v in voices}


def test_docs_hidden_in_production(monkeypatch):
    import main
    from settings import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "production")
    try:
        app = main.create_app()
        assert app.docs_url is None and app.openapi_url is None
    finally:
        get_settings.cache_clear()


def test_tts_wait_and_download(client):
    r = client.post("/api/tts?wait=true", json={"text": "पहला वाक्य। दूसरा वाक्य।", "voice": "hf_alpha"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and d["url"].endswith("format=mp3")
    # 2 × (1 s speech + 2×20 ms) + 250 ms pause, ≈ 2.3 s plus 100 ms edges
    assert 2.1 < d["duration_sec"] < 2.6
    assert d["loudness"]["target_lufs"] == -14.0
    assert d["loudness"]["output_true_peak"] <= -1.0
    wav = client.get(d["urls"]["wav"])
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav"
    import io
    pcm, sr = sf.read(io.BytesIO(wav.content))
    assert sr == 48000 and not pcm[: sr * 75 // 1000].any()   # ≥75 ms digital silence lead-in
    mp3 = client.get(d["url"] + "&download=true")
    assert mp3.headers["content-type"] == "audio/mpeg" and "attachment" in mp3.headers["content-disposition"]
    assert client.get(f"/api/tts/jobs/{d['id']}").json()["status"] == "done"


def test_tts_custom_loudness_and_off(client):
    r = client.post("/api/tts?wait=true", json={"text": "Hello there.", "voice": "af_heart",
                                                "loudness_lufs": -16})
    assert r.json()["loudness"]["target_lufs"] == -16
    r = client.post("/api/tts?wait=true", json={"text": "Hello there.", "voice": "af_heart",
                                                "normalize": False})
    assert r.json()["loudness"]["mode"] == "skipped"


def test_tts_async_returns_job(client):
    r = client.post("/api/tts", json={"text": "Hi.", "voice": "bf_emma", "format": "wav"})
    assert r.status_code in (200, 202) and "id" in r.json()


def test_validation(client):
    bad = [
        {"text": "", "voice": "hf_alpha"},
        {"text": "x" * 5001, "voice": "hf_alpha"},
        {"text": "hi", "voice": "nope"},
        {"text": "hi", "voice": "hf_alpha", "lang": "a"},
        {"text": "hi", "voice": "hf_alpha", "speed": 2},
        {"text": "hi", "voice": "hf_alpha", "format": "ogg"},
        {"text": "hi", "voice": "hf_alpha", "loudness_lufs": -3},
        {"text": "hi", "voice": "hf_alpha", "engine": "edge"},
        {"text": "hi", "voice": "hf_alpha", "transliterate": True},
    ]
    for body in bad:
        assert client.post("/api/tts", json=body).status_code == 422, body


def test_audio_path_traversal(client):
    for bad in ["../settings", "abc", "0" * 31 + "g", "..%2F..%2Fsettings.py"]:
        assert client.get(f"/api/audio/{bad}").status_code == 404
    assert client.get("/api/audio/" + "0" * 32 + "?format=py").status_code == 422
    assert client.get("/api/tts/jobs/" + "0" * 32).status_code == 404

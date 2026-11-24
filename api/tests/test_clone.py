"""Custom (clone) voices, phase 13: registry, consent gate, owner-only, two-stage queue, retry, no charge on failure."""
import json

import numpy as np
import pytest

from tests.conftest import ORIGIN, FakeEngine, _run, signup

VID = "hi_test_clone_m1"


class FakeCloner:
    """Stands in for the voice-clone worker (CloneClient interface)."""
    fail_times = 0          # convert() raises CloneError this many times before working
    calls = 0

    def __init__(self, url, secret, timeout):
        self.configured = bool(secret)

    def health(self):
        return {"status": "ok", "voices": [VID]}

    def convert(self, audio, sr, voice_id):
        from tts.clone_client import CloneError
        FakeCloner.calls += 1
        if FakeCloner.fail_times > 0:
            FakeCloner.fail_times -= 1
            raise CloneError("worker answered 503")
        out_sr = 22050
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * out_sr / sr)).astype(int)
        return audio[idx], out_sr


async def _add_consent(url, voice_id, status="active"):
    from db import make_engine, make_sessionmaker
    from models import VoiceConsent
    eng = make_engine(url)
    async with make_sessionmaker(eng)() as db:
        db.add(VoiceConsent(voice_id=voice_id, source_type="ai_voice", attestation_note="test", status=status))
        await db.commit()
    await eng.dispose()


@pytest.fixture
def clone_app(app_env, monkeypatch, tmp_path):
    """Client with one clone voice configured (no consent yet) and a fake worker."""
    import fakeredis
    import main
    from fastapi.testclient import TestClient
    from settings import get_settings

    vdir = tmp_path / "data" / "voices" / VID
    vdir.mkdir(parents=True)
    (vdir / "voice.json").write_text(json.dumps({
        "id": VID, "name": "Test Veer", "tags": ["energetic"], "reference_path": "ref.wav", "source_voice": "hm_omega",
        "default_style": "energetic-reel", "style_speed": {"energetic-reel": 1.08}, "default_speed": 1.08, "max_chars": 300}))
    (tmp_path / "data" / "voices" / "broken").mkdir()
    (tmp_path / "data" / "voices" / "broken" / "voice.json").write_text("{not json")
    monkeypatch.setenv("AIWAZZ_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AIWAZZ_CLONE_SECRET", "test-secret")
    get_settings.cache_clear()
    monkeypatch.setattr(main, "KokoroEngine", FakeEngine)
    monkeypatch.setattr(main, "CloneClient", FakeCloner)
    FakeCloner.fail_times, FakeCloner.calls = 0, 0
    app = main.create_app()
    app.state.redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as c:
        import time
        for _ in range(50):
            if c.get("/api/health").status_code == 200:
                break
            time.sleep(0.05)
        c.headers["X-CSRF-Token"] = c.get("/api/auth/csrf").json()["csrf_token"]
        c.consent = lambda status="active": _run(_add_consent(app_env, VID, status))
        yield c


def _ids(c):
    return [v["id"] for v in c.get("/api/voices").json()["voices"]]


def _spy(c):
    eng = c.app.state.jobs.engine
    said, orig = [], eng.synthesize

    def synth(sentence, voice, lang, speed):
        said.append((voice, speed))
        return orig(sentence, voice, lang, speed)
    eng.synthesize = synth
    return said


def test_clone_voice_needs_consent_and_is_owner_only(clone_app, make_invite):
    c = clone_app
    make_invite("ADMN-CODE", role="admin")
    make_invite("USER-CODE")
    assert VID not in _ids(c)                                   # signed out
    signup(c, code="ADMN-CODE")
    assert VID not in _ids(c)                                   # admin, but no consent record yet
    assert c.post("/api/tts", json={"text": "नमस्ते।", "voice": VID}).status_code == 422
    c.consent("pending")
    assert VID not in _ids(c)                                   # pending ≠ active
    c.consent("active")
    v = next(v for v in c.get("/api/voices").json()["voices"] if v["id"] == VID)
    assert v["engine"] == "clone" and v["tier"] == "studio" and v["is_public"] is False and v["max_chars"] == 300
    from settings import get_settings
    (get_settings().data_dir / "voices" / VID / "preview.mp3").write_bytes(b"ID3fake")
    assert c.get(v["preview_url"]).headers["content-type"] == "audio/mpeg"
    c.post("/api/auth/logout")
    assert c.get(v["preview_url"]).status_code == 404
    signup(c, email="u@example.com", code="USER-CODE")          # a regular user never sees an owner-only voice
    assert VID not in _ids(c)
    assert c.get(v["preview_url"]).status_code == 404
    r = c.post("/api/tts", json={"text": "नमस्ते।", "voice": VID})
    assert r.status_code == 422 and "unknown voice" in r.json()["detail"]


def test_clone_job_two_stages_default_style_and_charge(clone_app, make_invite):
    c = clone_app
    make_invite("ADMN-CODE", role="admin")
    signup(c, code="ADMN-CODE")
    c.consent()
    c.app.state.jobs.engine.ready = True
    said = _spy(c)
    text = "पहला वाक्य। दूसरा वाक्य।\n\nतीसरा।"
    r = c.post("/api/tts?wait=true", json={"text": text, "voice": VID})   # unchanged request shape
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and d["duration_sec"] > 1 and d["estimate_sec"] >= 10
    assert set(said) == {("hm_omega", 1.08)}                     # Kokoro read the source voice at Veer's reel speed
    assert FakeCloner.calls == 3                                  # every sentence went through the worker
    assert "convert_sec" in d["timing"] and d["loudness"]["target_lufs"] == -14.0
    for f in ("mp3", "wav"):
        a = c.get(f"/api/audio/{d['id']}?format={f}")
        assert a.status_code == 200 and len(a.content) > 1000
    h = c.get("/api/history").json()["items"][0]
    assert h["voice"] == VID and h["style"] == "energetic-reel"
    assert c.get("/api/usage").json()["used"] == len(text) == h["text_chars"]   # counted on the original script
    # An explicit style/speed still wins
    c.post("/api/tts?wait=true", json={"text": "धीरे।", "voice": VID, "style": "calm-narrator"})
    assert said[-1] == ("hm_omega", 0.92)


def test_clone_char_limit_and_worker_down(clone_app, make_invite, monkeypatch):
    c = clone_app
    make_invite("ADMN-CODE", role="admin")
    signup(c, code="ADMN-CODE")
    c.consent()
    r = c.post("/api/tts", json={"text": "क" * 301, "voice": VID})
    assert r.status_code == 422 and "300 characters" in r.json()["detail"]
    monkeypatch.setattr(c.app.state.jobs.cloner, "health", lambda: {"voices": []})
    assert c.post("/api/tts", json={"text": "नमस्ते।", "voice": VID}).status_code == 503


def test_clone_retries_once_then_fails_without_charge(clone_app, make_invite, set_plan):
    c = clone_app
    make_invite("ADMN-CODE", role="admin")
    signup(c, code="ADMN-CODE")
    c.consent()
    FakeCloner.fail_times = 1                                     # first attempt fails, the retry works
    r = c.post("/api/tts?wait=true", json={"text": "एक। दो।", "voice": VID})
    assert r.status_code == 200 and r.json()["status"] == "done"
    FakeCloner.fail_times = 99                                    # both attempts fail
    r = c.post("/api/tts?wait=true", json={"text": "तीन।", "voice": VID})
    assert r.status_code == 422 and "Nothing was charged" in r.json()["error"]
    items = c.get("/api/history").json()["items"]
    assert [i["status"] for i in items] == ["error", "done"]
    assert c.get("/api/usage").json()["used"] == len("एक। दो।")      # the failed job isn't charged


def test_kokoro_jobs_do_not_wait_for_conversions(clone_app, make_invite):
    """A clone job parked in the clone queue never holds the Kokoro queue."""
    import asyncio
    jm = clone_app.app.state.jobs
    from tts.jobs import Job, TTSRequest
    req = TTSRequest(text="x", engine="clone", voice=VID, lang="h", speed=1.0, format="mp3", loudness_lufs=None,
                     source_voice="hm_omega")
    job = Job(id="a" * 32, req=req, stage="studio-queue")
    jm.jobs[job.id] = job
    jm.clone_pending.append(job.id)
    assert jm.running is None and jm.status(job)["stage"] == "studio-queue" and jm.status(job)["position"] == 1
    jm.clone_pending.clear()


def test_worker_requires_secret(monkeypatch):
    from fastapi.testclient import TestClient
    from settings import get_settings
    from voiceclone import worker
    monkeypatch.setenv("AIWAZZ_CLONE_SECRET", "s3cret")
    get_settings.cache_clear()
    monkeypatch.setattr(worker.state, "load", lambda: None)
    with TestClient(worker.app) as c:
        assert c.get("/health").status_code == 401
        assert c.get("/health", headers={"X-Clone-Secret": "wrong"}).status_code == 401
        assert c.get("/health", headers={"X-Clone-Secret": "s3cret"}).status_code == 200
        assert c.post("/convert?voice_id=x", content=b"RIFF", headers={"X-Clone-Secret": "nope"}).status_code == 401
        assert c.post("/convert?voice_id=x", content=b"RIFF", headers={"X-Clone-Secret": "s3cret"}).status_code == 404
    get_settings.cache_clear()

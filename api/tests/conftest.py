import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))
os.environ["AIWAZZ_STORAGE_DIR"] = tempfile.mkdtemp(prefix="aiwazz-test-")
os.environ["AIWAZZ_ENV"] = "test"


def speechlike(seconds: float, sr: int = 24000, amp: float = 0.3, seed: int = 0) -> np.ndarray:
    """Noise with a 4 Hz syllable-like envelope: loudness behaves roughly like speech."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    env = 0.5 * (1 + np.sin(2 * np.pi * 4 * t))
    return (amp * env * rng.standard_normal(t.size)).astype(np.float32)


class FakeEngine:
    name = "kokoro"
    sample_rate = 24000
    ready = False

    def __init__(self, torch_threads: int = 1):
        pass

    def load(self):
        self.ready = True

    def synthesize(self, sentence, voice, lang, speed):
        pad = np.zeros(self.sample_rate // 2, dtype=np.float32)  # 0.5 s silence each side
        return np.concatenate([pad, speechlike(1.0, amp=0.05), pad])


ORIGIN = "https://login.aiwazz.in"


def _run(coro):
    import asyncio
    return asyncio.run(coro)


async def _setup_db(url: str) -> None:
    import models  # noqa: F401
    from db import Base, make_engine
    eng = make_engine(url)
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    await eng.dispose()


async def _add_invite(url: str, code: str, **kw) -> None:
    from auth.security import normalize_invite, sha256
    from db import make_engine, make_sessionmaker
    from models import Invite
    eng = make_engine(url)
    async with make_sessionmaker(eng)() as db:
        db.add(Invite(code_hash=sha256(normalize_invite(code)), **kw))
        await db.commit()
    await eng.dispose()


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    from settings import get_settings
    url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("AIWAZZ_DATABASE_URL", url)
    monkeypatch.setenv("AIWAZZ_STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    _run(_setup_db(url))
    yield url
    get_settings.cache_clear()


@pytest.fixture
def make_invite(app_env):
    def make(code="ABCD-EFGH", **kw):
        _run(_add_invite(app_env, code, **kw))
        return code
    return make


@pytest.fixture
def anon(app_env, monkeypatch):
    """Unauthenticated client (https, correct Origin) with a fake TTS engine and fake Redis."""
    import fakeredis
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "KokoroEngine", FakeEngine)
    app = main.create_app()
    app.state.redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as c:
        import time
        for _ in range(50):
            if c.get("/api/health").status_code == 200:
                break
            time.sleep(0.05)
        c.headers["X-CSRF-Token"] = c.get("/api/auth/csrf").json()["csrf_token"]
        yield c


def signup(c, email="me@example.com", password="correct horse battery", code="ABCD-EFGH"):
    r = c.post("/api/auth/signup", json={"email": email, "password": password, "invite_code": code, "accept_terms": True})
    if r.status_code == 201:  # CSRF cookie rotates with the new session
        c.headers["X-CSRF-Token"] = c.cookies.get("__Host-aiwazz_csrf")
    return r


@pytest.fixture
def client(anon, make_invite):
    """Signed-in client (regular user)."""
    make_invite()
    assert signup(anon).status_code == 201
    return anon


class identity:
    """Temporarily act as someone else on the same TestClient (same event loop as the app's worker):
    with identity(c): ...  -> no cookies, no CSRF/Origin headers (like a script using X-API-Key)."""

    def __init__(self, c, keep_origin: bool = False):
        self.c, self.keep_origin = c, keep_origin

    def __enter__(self):
        self.cookies = list(self.c.cookies.jar)  # full Cookie objects (keep domain/path)
        self.headers = dict(self.c.headers)
        self.c.cookies.clear()
        for h in ("x-csrf-token",) + (() if self.keep_origin else ("origin",)):
            self.c.headers.pop(h, None)
        return self.c

    def __exit__(self, *exc):
        self.c.cookies.clear()
        for ck in self.cookies:
            self.c.cookies.jar.set_cookie(ck)
        self.c.headers.clear()
        self.c.headers.update(self.headers)

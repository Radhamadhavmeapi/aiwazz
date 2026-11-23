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


@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "KokoroEngine", FakeEngine)
    with TestClient(main.create_app()) as c:
        import time
        for _ in range(50):
            if c.get("/api/health").status_code == 200:
                break
            time.sleep(0.05)
        yield c

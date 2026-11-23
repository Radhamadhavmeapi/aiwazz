"""Kokoro-82M on CPU. One shared KModel for all language pipelines (saves ~600 MB per language)."""
import logging
import time

import numpy as np

from .voices import LANGS

log = logging.getLogger(__name__)
REPO_ID = "hexgrad/Kokoro-82M"


class KokoroEngine:
    name = "kokoro"
    sample_rate = 24000

    def __init__(self, torch_threads: int):
        self.torch_threads = torch_threads
        self.pipelines: dict = {}

    def load(self) -> None:
        import torch
        from kokoro import KModel, KPipeline

        t0 = time.perf_counter()
        torch.set_num_threads(self.torch_threads)
        model = KModel(repo_id=REPO_ID).eval()
        self.pipelines = {lang: KPipeline(lang_code=lang, repo_id=REPO_ID, model=model) for lang in LANGS}
        log.info("kokoro loaded (%s) in %.1fs", ",".join(self.pipelines), time.perf_counter() - t0)

    @property
    def ready(self) -> bool:
        return bool(self.pipelines)

    def synthesize(self, sentence: str, voice: str, lang: str, speed: float) -> np.ndarray:
        """Synthesize one sentence → float32 mono at 24 kHz. Blocking; call from a worker thread."""
        import torch

        pipeline = self.pipelines[lang]
        chunks = []
        with torch.inference_mode():
            # split_pattern=None: we already split into sentences ourselves.
            for result in pipeline(sentence, voice=voice, speed=speed, split_pattern=None):
                if result.audio is not None:
                    chunks.append(result.audio.numpy())
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

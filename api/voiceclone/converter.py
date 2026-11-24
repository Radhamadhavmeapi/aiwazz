"""OpenVoice v2 tone colour converter (route A of phase 13): Kokoro audio in, the target voice's timbre out.

Pure inference wrapper: no FastAPI here, so tests and the prepare script can use it directly.
"""
import logging
import time
from pathlib import Path

import numpy as np
import soxr
import torch

from .openvoice.mel import spectrogram
from .openvoice.models import SynthesizerTrn
from .openvoice.utils import get_hparams_from_file

log = logging.getLogger(__name__)


class ToneConverter:
    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.model: SynthesizerTrn | None = None
        self.hps = None

    @property
    def sample_rate(self) -> int:
        return self.hps.data.sampling_rate

    def load(self) -> float:
        t0 = time.perf_counter()
        hps = get_hparams_from_file(str(self.model_dir / "config.json"))
        model = SynthesizerTrn(len(getattr(hps, "symbols", [])), hps.data.filter_length // 2 + 1,
                               n_speakers=hps.data.n_speakers, **hps.model)
        ck = torch.load(self.model_dir / "checkpoint.pth", map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model"], strict=False)
        self.model, self.hps = model.eval(), hps
        return time.perf_counter() - t0

    def _spec(self, audio: np.ndarray, sr: int) -> torch.Tensor:
        if sr != self.sample_rate:
            audio = soxr.resample(audio.astype(np.float32), sr, self.sample_rate)
        y = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))[None]
        d = self.hps.data
        return spectrogram(y, d.filter_length, d.hop_length, d.win_length)

    @torch.inference_mode()
    def embedding(self, clips: list[tuple[np.ndarray, int]]) -> torch.Tensor:
        """Tone colour (speaker embedding) = mean of the reference encoder over the clips."""
        gs = [self.model.ref_enc(self._spec(a, sr).transpose(1, 2)).unsqueeze(-1) for a, sr in clips]
        return torch.stack(gs).mean(0)

    @torch.inference_mode()
    def convert(self, audio: np.ndarray, sr: int, src_se: torch.Tensor, tgt_se: torch.Tensor, tau: float = 0.3) -> np.ndarray:
        """Returns float32 mono at self.sample_rate (22.05 kHz)."""
        spec = self._spec(audio, sr)
        lengths = torch.LongTensor([spec.size(-1)])
        out = self.model.voice_conversion(spec, lengths, sid_src=src_se, sid_tgt=tgt_se, tau=tau)[0][0, 0]
        return out.float().numpy()

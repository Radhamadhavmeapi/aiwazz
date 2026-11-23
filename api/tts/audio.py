"""Audio post-processing: silence trim, joining, two-pass EBU R128 loudnorm, WAV/MP3 export (ffmpeg)."""
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

FFMPEG = "ffmpeg"
_FRAME_MS = 10


class AudioError(RuntimeError):
    pass


def trim_silence(audio: np.ndarray, sr: int, threshold_db: float, keep_ms: int) -> np.ndarray:
    """Remove leading/trailing silence, keeping `keep_ms` of it at each edge.

    Silence = 10 ms frames whose RMS is below `threshold_db` dBFS.
    """
    if audio.size == 0:
        return audio
    frame = max(1, sr * _FRAME_MS // 1000)
    n_frames = math.ceil(audio.size / frame)
    padded = np.pad(audio, (0, n_frames * frame - audio.size))
    rms = np.sqrt(np.mean(padded.reshape(n_frames, frame) ** 2, axis=1))
    loud = np.flatnonzero(rms > 10 ** (threshold_db / 20))
    if loud.size == 0:
        return audio[:0]
    keep = sr * keep_ms // 1000
    start = max(0, loud[0] * frame - keep)
    end = min(audio.size, (loud[-1] + 1) * frame + keep)
    return audio[start:end]


def pad_edges(audio: np.ndarray, sr: int, pad_ms: int, fade_ms: int = 10) -> np.ndarray:
    """Short fade in/out (no clicks), then `pad_ms` of digital silence at both ends."""
    a = audio.astype(np.float32, copy=True)
    n = min(sr * fade_ms // 1000, a.size // 2)
    if n:
        ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))).astype(np.float32)
        a[:n] *= ramp
        a[-n:] *= ramp[::-1]
    pad = np.zeros(sr * pad_ms // 1000, dtype=np.float32)
    return np.concatenate([pad, a, pad])


def join_segments(paragraphs: list[list[np.ndarray]], sr: int,
                  sentence_pause_ms: int, paragraph_pause_ms: int) -> np.ndarray:
    """Concatenate sentence clips with fixed pauses (longer between paragraphs)."""
    s_gap = np.zeros(sr * sentence_pause_ms // 1000, dtype=np.float32)
    p_gap = np.zeros(sr * paragraph_pause_ms // 1000, dtype=np.float32)
    parts: list[np.ndarray] = []
    for pi, para in enumerate(paragraphs):
        if pi:
            parts.append(p_gap)
        for si, clip in enumerate(para):
            if si:
                parts.append(s_gap)
            parts.append(clip.astype(np.float32, copy=False))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _run(args: list[str]) -> str:
    """Run ffmpeg (argument list, no shell); return stderr."""
    proc = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-nostats", *args],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {proc.stderr[-800:]}")
    return proc.stderr


_SUMMARY_I = re.compile(r"Integrated loudness:\s+I:\s+(-?[\d.]+|-inf|nan) LUFS")
_SUMMARY_TP = re.compile(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf|nan) dBFS")


def _num(v: str | None) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > -69.0 else None  # ebur128 reports -70 for "no signal"


def measure(path: Path, af: str | None = None) -> tuple[float | None, float | None]:
    """EBU R128 integrated loudness (LUFS) and true peak (dBTP) of `path` (optionally after filter `af`)."""
    chain = f"{af}," if af else ""
    err = _run(["-i", str(path), "-af", f"{chain}ebur128=peak=true:framelog=quiet", "-f", "null", "-"])
    summary = err[err.rfind("Summary:"):]
    i, tp = _SUMMARY_I.search(summary), _SUMMARY_TP.search(summary)
    return _num(i and i.group(1)), _num(tp and tp.group(1))


@dataclass
class Loudness:
    target_lufs: float | None
    input_lufs: float | None
    input_true_peak: float | None
    output_lufs: float | None
    output_true_peak: float | None
    gain_db: float | None
    compressor: bool = False
    limiter_reduction_db: float | None = None  # how much the limiter had to take off the peaks
    mode: str = "skipped"  # "linear", "linear+limiter" or "skipped"


@dataclass(frozen=True)
class Compressor:
    """Gentle RMS compressor applied *before* the gain stage, threshold relative to the clip's loudness.

    Being before the (linear) gain, the gain search stays linear and converges; being relative,
    it acts the same on quiet and loud voices. Takes the bulk off loud syllables so the
    limiter only has to catch fast transients (≈ halves limiter work on quiet voices).
    """
    threshold_rel_db: float = 0.0
    ratio: float = 2.0
    attack_ms: float = 10.0
    release_ms: float = 150.0
    knee: float = 6.0

    def filter(self, input_lufs: float) -> str:
        th = min(0.0, input_lufs + self.threshold_rel_db)
        return (f"acompressor=threshold={th:.2f}dB:ratio={self.ratio}:attack={self.attack_ms}"
                f":release={self.release_ms}:knee={self.knee}:detection=rms:makeup=1")


def _gain_chain(pre: str | None, gain_db: float, ceiling_db: float | None, sample_rate: int) -> str:
    # [compressor] → linear gain → lookahead limiter at 4x oversampling so *true* peaks stay under the ceiling.
    parts = [pre] if pre else []
    parts.append(f"volume={gain_db:.3f}dB")
    if ceiling_db is not None:
        limit = max(0.0625, 10 ** (ceiling_db / 20))
        parts += [f"aresample={sample_rate * 4}:resampler=soxr",
                  f"alimiter=limit={limit:.5f}:attack=1:release=60:level=0:latency=1",
                  f"aresample={sample_rate}:resampler=soxr"]
    return ",".join(parts)


def normalize_plan(src: Path, sample_rate: int, target_lufs: float, true_peak: float,
                   compressor: Compressor | None = None, margin_db: float = 0.3,
                   tolerance: float = 0.2, max_iter: int = 4) -> tuple[str | None, Loudness]:
    """Two-pass loudness normalisation.

    Pass 1 measures integrated loudness + true peak. Pass 2 applies an optional gentle compressor,
    the exact linear gain to reach the target and, if peaks would exceed the ceiling, a true-peak
    limiter. Compression/limiting change loudness slightly, so the gain is re-measured and corrected
    (usually 1-2 rounds). Unlike ffmpeg loudnorm, this never falls back to dynamic (AGC) mode and
    works on clips < 3 s.
    """
    i0, tp0 = measure(src)
    loud = Loudness(target_lufs, i0, tp0, None, None, None)
    if i0 is None:  # silent / too short to measure
        return None, loud
    ceiling = true_peak - margin_db  # headroom for 16-bit + MP3 encoding overs
    pre = compressor.filter(i0) if compressor else None
    gain = target_lufs - i0
    af = None
    for _ in range(max_iter):
        af = _gain_chain(pre, gain, ceiling, sample_rate)
        i, _tp = measure(src, af)
        if i is None or abs(target_lufs - i) <= tolerance:
            break
        gain += target_lufs - i
    _, tp_pre = measure(src, _gain_chain(pre, gain, None, sample_rate))  # peaks before the limiter
    reduction = max(0.0, tp_pre - ceiling) if tp_pre is not None else 0.0
    loud.gain_db, loud.compressor = round(gain, 2), compressor is not None
    loud.limiter_reduction_db = round(reduction, 1)
    loud.mode = "linear+limiter" if reduction > 0.05 else "linear"
    return af, loud


def export(audio: np.ndarray, sr: int, out_base: Path, *, sample_rate: int, mp3_bitrate: str,
           target_lufs: float | None, true_peak: float, compressor: Compressor | None = None) -> Loudness:
    """Write <out_base>.wav (16-bit PCM, mono) and <out_base>.mp3 at `sample_rate`.

    With `target_lufs` set, normalises loudness to it with true peak ≤ `true_peak` dBTP.
    """
    wav_out, mp3_out = out_base.with_suffix(".wav"), out_base.with_suffix(".mp3")
    with tempfile.TemporaryDirectory(prefix="aiwazz-") as tmp:
        raw, up = Path(tmp) / "raw.wav", Path(tmp) / "up.wav"
        sf.write(raw, audio, sr, subtype="FLOAT")
        # Resample once to the output rate (float, no clipping); all loudness work happens at that rate.
        _run(["-y", "-i", str(raw), "-af", f"aresample={sample_rate}:resampler=soxr", "-ac", "1",
              "-c:a", "pcm_f32le", str(up)])
        af, loud = None, Loudness(None, None, None, None, None, None)
        if target_lufs is not None:
            af, loud = normalize_plan(up, sample_rate, target_lufs, true_peak, compressor)
        args = ["-y", "-i", str(up)] + (["-af", af] if af else [])
        _run(args + ["-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le", str(wav_out)])

    if af:
        loud.output_lufs, loud.output_true_peak = measure(wav_out)
    _run(["-y", "-i", str(wav_out), "-c:a", "libmp3lame", "-b:a", mp3_bitrate,
          "-ar", str(sample_rate), str(mp3_out)])
    return loud

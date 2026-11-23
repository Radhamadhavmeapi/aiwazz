"""Phase 1 benchmark: synthesize Hindi + English test WAVs with Kokoro on CPU.

Usage: .venv/bin/python scripts/bench_kokoro.py <out_dir>
Reports realtime factor (seconds of audio per second of compute) and peak RAM.
"""
import resource
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from kokoro import KModel, KPipeline

SR = 24000
TESTS = [
    ("h", "hf_alpha", "नमस्ते दोस्तों! आज हम बात करेंगे कि छोटे वीडियो के लिए अच्छा वॉइसओवर कैसे बनाएं। "
                      "रात ग्यारह बजे कस्टमर ने कॉल किया और कहा कि उसका ऑर्डर अभी तक नहीं आया।"),
    ("h", "hm_omega", "यह आवाज़ पूरी तरह से कंप्यूटर पर बनाई गई है, बिना किसी जीपीयू के।"),
    ("a", "af_heart", "Hello! This is a quick test of AI voiceovers for short videos. "
                      "It runs entirely on a CPU, with no GPU at all."),
    ("b", "bf_emma", "And this is the British English voice, reading the same kind of short script."),
]


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    print(f"torch {torch.__version__}, threads={torch.get_num_threads()}")

    # One shared model for all languages: ~1.3 GB RSS instead of ~600 MB extra per pipeline.
    model = KModel(repo_id="hexgrad/Kokoro-82M").eval()
    print(f"load model: peak RSS {rss_mb():.0f} MB")
    pipelines = {}
    for lang in sorted({t[0] for t in TESTS}):
        t0 = time.perf_counter()
        pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", model=model)
        print(f"load lang={lang}: {time.perf_counter() - t0:.1f}s, peak RSS {rss_mb():.0f} MB")

    total_audio = total_compute = 0.0
    for i, (lang, voice, text) in enumerate(TESTS):
        t0 = time.perf_counter()
        chunks = [a.numpy() if hasattr(a, "numpy") else a
                  for _, _, a in pipelines[lang](text, voice=voice, speed=1.0)]
        audio = np.concatenate(chunks)
        dt = time.perf_counter() - t0
        dur = len(audio) / SR
        name = out_dir / f"{i + 1}_{lang}_{voice}.wav"
        sf.write(name, audio, SR)
        total_audio += dur
        total_compute += dt
        print(f"{name.name}: {dur:.1f}s audio in {dt:.1f}s -> {dur / dt:.2f}x realtime, "
              f"peak RSS {rss_mb():.0f} MB")

    print(f"TOTAL: {total_audio:.1f}s audio in {total_compute:.1f}s -> "
          f"{total_audio / total_compute:.2f}x realtime; peak RSS {rss_mb():.0f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "bench_out"))

"""Route A input + Kokoro baseline. Runs with the API venv (kokoro installed there), separate process."""
import json, sys, time
import numpy as np, soundfile as sf
sys.path.insert(0, "/root/voicelab")
from common import OUT, SCRIPTS, prepare, start_watchdog, peak_rss_mb, require_free, postprocess
require_free(1500); wd = start_watchdog()
import torch
torch.set_num_threads(4)
from kokoro import KModel, KPipeline
t0 = time.perf_counter()
model = KModel(repo_id="hexgrad/Kokoro-82M").eval()
pipe = KPipeline(lang_code="h", repo_id="hexgrad/Kokoro-82M", model=model)
load = time.perf_counter() - t0
stats = {"load_sec": round(load, 1)}
for voice in ("hm_omega", "hm_psi"):
    for key, (_, text) in SCRIPTS.items():
        speed = 1.0 if key == "5-calm" else 1.1
        paras = prepare(text, digits_to_words=False)   # production path: Kokoro/espeak reads digits itself
        t = time.perf_counter(); clips = []
        with torch.inference_mode():
            for para in paras:
                row = []
                for s in para:
                    row.append(np.concatenate([r.audio.numpy() for r in pipe(s, voice=voice, speed=speed, split_pattern=None) if r.audio is not None]))
                clips.append(row)
        synth = time.perf_counter() - t
        base = OUT / "kokoro" / voice / key
        dur = postprocess(clips, 24000, base)
        # raw source for voice conversion: same trims/pauses, no loudness change
        from tts import audio
        raw = audio.join_segments([[audio.trim_silence(c, 24000, -45.0, keep_ms=20) for c in p] for p in clips], 24000, 250, 600)
        sf.write(base.with_suffix(".src.wav"), raw, 24000, subtype="FLOAT")
        stats[f"{voice}/{key}"] = {"audio_sec": round(dur, 2), "synth_sec": round(synth, 2), "rtf": round(synth / dur, 3), "speed": speed}
        print(voice, key, stats[f"{voice}/{key}"], flush=True)
stats["peak_rss_mb"] = peak_rss_mb(); stats["min_mem_available_mb"] = wd["min_avail"]
json.dump(stats, open(OUT / "kokoro" / "stats.json", "w"), indent=1)
print(stats["peak_rss_mb"], "MB peak RSS; min available", wd["min_avail"])

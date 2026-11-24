"""Route A: Kokoro → OpenVoice v2 tone colour converter (MIT). Voice-lab venv."""
import json, sys, time, types
sys.path.insert(0, "/root/voicelab"); sys.path.insert(0, "/root/voicelab/ov")
from common import OUT, REFS, SCRIPTS, start_watchdog, peak_rss_mb, require_free, postprocess
require_free(800); wd = start_watchdog()
stub = types.ModuleType("openvoice.text"); stub.text_to_sequence = lambda *a, **k: []; sys.modules["openvoice.text"] = stub
import torch; torch.set_num_threads(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
import soundfile as sf
import openvoice.api as _ova
_orig = _ova.OpenVoiceBaseClass.__init__
_ova.OpenVoiceBaseClass.__init__ = lambda self, cfg, device="cpu", **kw: _orig(self, cfg, device)
from openvoice.api import ToneColorConverter
M = "/root/voicelab/models/openvoice"
t0 = time.perf_counter()
tcc = ToneColorConverter(f"{M}/config.json", device="cpu", enable_watermark=False); tcc.load_ckpt(f"{M}/checkpoint.pth")
load = time.perf_counter() - t0
kstats = json.load(open(OUT / "kokoro" / "stats.json"))
stats = {"load_sec": round(load, 2), "threads": torch.get_num_threads()}
t = time.perf_counter(); tgt = {c: tcc.extract_se([str(p)]) for c, p in REFS.items()}; stats["target_se_sec"] = round(time.perf_counter() - t, 2)
for voice in ("hm_omega", "hm_psi"):
    srcs = [str(OUT / "kokoro" / voice / f"{k}.src.wav") for k in SCRIPTS]
    src_se = tcc.extract_se(srcs)
    for clip in ("A", "B"):
        for key in SCRIPTS:
            t = time.perf_counter()
            wav = tcc.convert(str(OUT / "kokoro" / voice / f"{key}.src.wav"), src_se, tgt[clip], tau=0.3)
            conv = time.perf_counter() - t
            sr = tcc.hps.data.sampling_rate
            dur = postprocess([[wav]], sr, OUT / "routeA" / f"{voice}-{clip}" / key, sentence_ms=0, paragraph_ms=0)
            k = kstats[f"{voice}/{key}"]
            s = {"audio_sec": round(dur, 2), "convert_sec": round(conv, 2), "convert_rtf": round(conv / dur, 3),
                 "total_rtf": round((conv + k["synth_sec"]) / dur, 3)}
            stats[f"{voice}-{clip}/{key}"] = s; print(voice, clip, key, s, flush=True)
stats["peak_rss_mb"] = peak_rss_mb(); stats["min_mem_available_mb"] = wd["min_avail"]
json.dump(stats, open(OUT / "routeA_stats.json", "w"), indent=1)
print("load", stats["load_sec"], "s; peak RSS", stats["peak_rss_mb"], "MB; min available", wd["min_avail"])

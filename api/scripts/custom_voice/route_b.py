"""Route B: Chatterbox Multilingual (MIT), zero-shot clone from clip A / B. Weights are memory-mapped from disk
(file-backed pages the kernel can drop and re-read), so the 3.2 GB model never becomes 3.2 GB of anonymous RAM."""
import json, mmap, struct, sys, time, warnings
warnings.filterwarnings("ignore", message=".*non-writable.*")
sys.path.insert(0, "/root/voicelab")
from common import OUT, REFS, SCRIPTS, prepare, start_watchdog, peak_rss_mb, require_free, postprocess, mem_available_mb
require_free(2600); wd = start_watchdog(600)
import torch
THREADS = int(sys.argv[1]); CLIPS = sys.argv[2].split(","); KEYS = sys.argv[3].split(",") if len(sys.argv) > 3 else list(SCRIPTS)
EXAG = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
TAG = sys.argv[5] if len(sys.argv) > 5 else ""
torch.set_num_threads(THREADS)
import chatterbox.mtl_tts as M
D = "/root/voicelab/models/chatterbox"
DT = {"F32": torch.float32, "F16": torch.float16, "BF16": torch.bfloat16, "I64": torch.int64}


def mmap_safetensors(path):
    f = open(path, "rb"); n = struct.unpack("<Q", f.read(8))[0]; header = json.loads(f.read(n))
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)   # shared read-only, file-backed (weights are never written)
    out = {}
    for k, v in header.items():
        if k == "__metadata__":
            continue
        a, b = v["data_offsets"]; dt = DT[v["dtype"]]
        t = torch.frombuffer(mm, dtype=dt, count=(b - a) // dt.itemsize, offset=8 + n + a)
        out[k] = t.view(v["shape"]) if v["shape"] else t.reshape(())
    return out


def rss():
    s = dict(l.split(":", 1) for l in open("/proc/self/status") if l.startswith(("RssAnon", "RssFile")))
    return {k: v.strip() for k, v in s.items()}


t0 = time.perf_counter()
ve = M.VoiceEncoder(); ve.load_state_dict(torch.load(f"{D}/ve.pt", map_location="cpu", weights_only=True)); ve.eval()
t3 = M.T3(M.T3Config.multilingual()); t3.load_state_dict(mmap_safetensors(f"{D}/t3_mtl23ls_v2.safetensors"), assign=True); t3.eval()
print("t3 loaded", rss(), "avail", mem_available_mb(), flush=True)
s3 = M.S3Gen(); s3.load_state_dict(torch.load(f"{D}/s3gen.pt", map_location="cpu", weights_only=True, mmap=True), assign=True); s3.eval()
tok = M.MTLTokenizer(f"{D}/grapheme_mtl_merged_expanded_v1.json")
tts = M.ChatterboxMultilingualTTS(t3, s3, ve, tok, "cpu", conds=M.Conditionals.load(f"{D}/conds.pt", map_location="cpu"))
load = time.perf_counter() - t0
print(f"loaded in {load:.1f}s", rss(), "avail", mem_available_mb(), flush=True)
sf_path = OUT / f"routeB_stats{TAG}.json"
stats = json.load(open(sf_path)) if sf_path.exists() else {}
stats.update({"load_sec": round(load, 1), "threads": THREADS, "exaggeration": EXAG})
for clip in CLIPS:
    t = time.perf_counter(); tts.prepare_conditionals(str(REFS[clip]), exaggeration=EXAG); cond = time.perf_counter() - t
    stats[f"cond_sec_{clip}"] = round(cond, 2)
    for key in KEYS:
        paras = prepare(SCRIPTS[key][1], digits_to_words=True)
        t = time.perf_counter(); clips = []
        for para in paras:
            row = []
            for s in para:
                torch.manual_seed(1234)
                row.append(tts.generate(s, language_id="hi", exaggeration=EXAG).squeeze(0).numpy())
            clips.append(row)
        synth = time.perf_counter() - t
        dur = postprocess(clips, tts.sr, OUT / f"routeB{TAG}" / clip / key)
        s = {"audio_sec": round(dur, 2), "synth_sec": round(synth, 1), "rtf": round(synth / dur, 2)}
        stats[f"{clip}/{key}"] = s
        print(clip, key, s, rss(), "avail", mem_available_mb(), flush=True)
        stats["peak_rss_mb"] = peak_rss_mb(); stats["min_mem_available_mb"] = wd["min_avail"]
        json.dump(stats, open(sf_path, "w"), indent=1)
print("done; peak RSS", peak_rss_mb(), "min avail", wd["min_avail"])

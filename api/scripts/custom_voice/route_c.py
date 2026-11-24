"""Route C (CPU, no training): Kokoro → kNN-VC (MIT; WavLM-Large MIT) matching against the narrator's own audio."""
import json, sys, time
sys.path.insert(0, "/root/voicelab")
from common import OUT, REFS, VOICE, SCRIPTS, start_watchdog, peak_rss_mb, require_free, postprocess
require_free(2200); wd = start_watchdog()
import torch; torch.set_num_threads(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
SRC = sys.argv[2] if len(sys.argv) > 2 else "hm_omega"
t0 = time.perf_counter()
sys.path.insert(0, "/root/voicelab/knnvc")
import librosa
from hubconf import hifigan_wavlm
from matcher import KNeighborsVC
import wavlm.WavLM as _W
from wavlm.WavLM import WavLM, WavLMConfig
_W.init_bert_params = lambda m: None   # random init is pointless (checkpoint overwrites) and fails on meta
hifigan, hcfg = hifigan_wavlm(True, False, True, "cpu")
# WavLM: build on the meta device and assign the checkpoint tensors (one copy of the 1.26 GB weights, not two)
ck = torch.load(str(__import__("pathlib").Path.home() / ".cache/torch/hub/checkpoints/WavLM-Large.pt"), map_location="cpu", weights_only=False)
with torch.device("meta"):
    wavlm = WavLM(WavLMConfig(ck["cfg"]))
wavlm.load_state_dict(ck["model"], assign=True); del ck
wavlm.eval()
knn = KNeighborsVC(wavlm, hifigan, hcfg, "cpu")
CH = 10 * 16000   # WavLM attention is O(T^2): feed ≤10 s chunks


from matcher import fast_cosine_dist


@torch.inference_mode()
def convert(q, ms, topk=4, win=500, ov=25):
    """kNN match, then vocode in ≤10 s windows (HiFiGAN activations grow with length) with a linear crossfade."""
    best = fast_cosine_dist(q, ms, device="cpu").topk(k=topk, largest=False, dim=-1)
    f = ms[best.indices].mean(dim=1)
    hop = 320; out = None
    for s0 in range(0, f.shape[0], win - ov):
        y = knn.vocode(f[s0:s0 + win][None]).squeeze().cpu()
        if out is None:
            out = y
        else:
            n = min(ov * hop, len(y), len(out)); r = torch.linspace(0, 1, n)
            out = torch.cat([out[:-n], out[-n:] * (1 - r) + y[:n] * r, y[n:]])
        if s0 + win >= f.shape[0]:
            break
    return out


def feats(path):
    x, _ = librosa.load(str(path), sr=16000, mono=True)
    x = torch.from_numpy(x)
    return torch.cat([knn.get_features(x[i:i + CH][None], vad_trigger_level=0) for i in range(0, len(x), CH) if len(x[i:i + CH]) > 1600])
load = time.perf_counter() - t0
kstats = json.load(open(OUT / "kokoro" / "stats.json"))
stats = {"load_sec": round(load, 1), "threads": torch.get_num_threads(), "source_voice": SRC}
sets = {"A": [str(REFS["A"])], "B": [str(REFS["B"])], "full": [str(VOICE / "voice_clean_full.wav")]}
for name, files in sets.items():
    t = time.perf_counter(); ms = torch.cat([feats(f) for f in files]); stats[f"matching_set_sec_{name}"] = round(time.perf_counter() - t, 1)
    for key in SCRIPTS:
        t = time.perf_counter()
        q = feats(OUT / "kokoro" / SRC / f"{key}.src.wav")
        wav = convert(q, ms).numpy()
        conv = time.perf_counter() - t
        dur = postprocess([[wav]], 16000, OUT / "routeC" / f"{SRC}-{name}" / key, sentence_ms=0, paragraph_ms=0)
        k = kstats[f"{SRC}/{key}"]
        s = {"audio_sec": round(dur, 2), "convert_sec": round(conv, 2), "convert_rtf": round(conv / dur, 3),
             "total_rtf": round((conv + k["synth_sec"]) / dur, 3)}
        stats[f"{SRC}-{name}/{key}"] = s; print(name, key, s, flush=True)
stats["peak_rss_mb"] = peak_rss_mb(); stats["min_mem_available_mb"] = wd["min_avail"]
json.dump(stats, open(OUT / "routeC_stats.json", "w"), indent=1)
print("load", stats["load_sec"], "peak", stats["peak_rss_mb"], "min avail", wd["min_avail"])

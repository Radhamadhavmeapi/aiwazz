"""Intelligibility (faster-whisper small, hi → CER) + speaker similarity (Chatterbox voice encoder, cosine) for every sample."""
import json, re, sys, unicodedata
sys.path.insert(0, "/root/voicelab")
from common import OUT, REFS, VOICE, SCRIPTS, spoken_text, start_watchdog, require_free
require_free(900); start_watchdog()
import numpy as np, librosa, torch, jiwer
torch.set_num_threads(4)
from faster_whisper import WhisperModel
from safetensors.torch import load_file
from chatterbox.models.voice_encoder import VoiceEncoder

# English words in the scripts as Whisper writes them in Devanagari (so Hinglish isn't punished for script choice)
LATIN = {"workout": "वर्कआउट", "plan": "प्लान", "simple": "सिंपल", "exercises": "एक्सरसाइज़", "minute": "मिनट",
         "zero": "ज़ीरो", "excuses": "एक्सक्यूज़", "let's": "लेट्स", "lets": "लेट्स", "go": "गो", "diet": "डाइट"}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t).lower()
    t = re.sub(r"[a-z']+", lambda m: LATIN.get(m.group(0), m.group(0)), t)
    t = unicodedata.normalize("NFD", t).replace("़", "")          # drop nukta (ज़ = ज for scoring)
    t = t.replace("ँ", "ं")                                   # chandrabindu → anusvara
    t = re.sub(r"[^\w\s]|_", " ", t)
    return re.sub(r"\s+", " ", t).strip()


wm = WhisperModel("/root/voicelab/models/whisper-small", device="cpu", compute_type="int8", cpu_threads=4)
ve = VoiceEncoder(); ve.load_state_dict(load_file("/root/voicelab/models/chatterbox/ve.safetensors")); ve.eval()


def embed(path):
    w, _ = librosa.load(str(path), sr=16000)
    with torch.inference_mode():
        e = ve.embeds_from_wavs([w], sample_rate=16000, as_spk=True)
    e = np.asarray(e).reshape(-1)
    return e / np.linalg.norm(e)


target = {k: embed(p) for k, p in REFS.items()}
target["full"] = embed(VOICE / "voice_clean_full.wav")
results = json.load(open(OUT / "eval.json")) if (OUT / "eval.json").exists() else {}
results["_refs"] = {"A~B": round(float(target["A"] @ target["B"]), 3), "A~full": round(float(target["A"] @ target["full"]), 3),
                    "B~full": round(float(target["B"] @ target["full"]), 3)}
only = sys.argv[1:]  # optional route dirs to (re)evaluate
for wav in sorted(OUT.glob("*/*/*.wav")):
    if wav.name.endswith(".src.wav") or (only and wav.parts[-3] not in only):
        continue
    key = wav.stem
    if key not in SCRIPTS:
        continue
    segs, _ = wm.transcribe(librosa.load(str(wav), sr=16000)[0], language="hi", beam_size=5, vad_filter=False)
    hyp = " ".join(s.text for s in segs)
    ref = spoken_text(SCRIPTS[key][1])
    cer = jiwer.cer(norm(ref), norm(hyp))
    e = embed(wav)
    rid = f"{wav.parts[-3]}/{wav.parts[-2]}/{key}"
    results[rid] = {"cer": round(cer, 3), "sim_full": round(float(e @ target["full"]), 3),
                    "sim_A": round(float(e @ target["A"]), 3), "sim_B": round(float(e @ target["B"]), 3), "asr": hyp.strip()}
    print(rid, results[rid]["cer"], results[rid]["sim_full"], flush=True)
    json.dump(results, open(OUT / "eval.json", "w"), ensure_ascii=False, indent=1)
# Calibration: Whisper on the narrator's own clips
for c in ("A", "B"):
    segs, _ = wm.transcribe(librosa.load(str(REFS[c]), sr=16000)[0], language="hi", beam_size=5)
    from common import REF_TEXT
    results[f"_ref_cer_{c}"] = round(jiwer.cer(norm(REF_TEXT[c]), norm(" ".join(s.text for s in segs))), 3)
json.dump(results, open(OUT / "eval.json", "w"), ensure_ascii=False, indent=1)
print("refs", results["_refs"], results["_ref_cer_A"], results["_ref_cer_B"])

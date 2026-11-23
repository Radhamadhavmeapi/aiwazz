"""Voice Lab (phase 10, track A): new Indian voices from Kokoro without new models.

Generates candidate samples with the SAME post-processing as production (sentence split, per-sentence trim,
fixed pauses, fades, two-pass loudness with compressor + true-peak limiter, MP3 48 kHz) and writes
<out>/<id>.mp3 + <out>/manifest.json (RTF, peak RAM, settings). Nothing here touches the product.

Usage: .venv/bin/python scripts/voice_lab.py <out_dir>
"""
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kokoro import KModel, KPipeline  # noqa: E402

from tts import audio  # noqa: E402
from tts.text import normalize, split_text  # noqa: E402

SR = 24000
TEST_SET = [
    ("Hindi", "नमस्ते दोस्तों! आज हम सीखेंगे कि अपनी रील के लिए साफ़ और दमदार आवाज़ कैसे बनाएँ।"),
    ("Hindi", "कहानी अभी बाक़ी है, इसलिए वीडियो आख़िर तक ज़रूर देखिए।"),
    ("Hinglish", "आज का offer सिर्फ़ 24 घंटे के लिए है, तो जल्दी order कीजिए।"),
    ("Hinglish", "Customer ने बताया कि delivery time पर हुई और packaging भी बढ़िया थी।"),
    ("Indian English", "Hello everyone, welcome back to the channel. Today we're talking about saving money on your monthly bills."),
    ("Indian English", "Please keep your booking ID ready when you call our support team."),
    ("Numbers & ₹", "यह प्लान सिर्फ़ ₹499 प्रति महीना है, और आप 2,00,000 characters तक इस्तेमाल कर सकते हैं।"),
]

# (id, name, description, voice spec [(voice, weight)], preset)
DEFAULT = {"speed": 1.0, "sentence_ms": 250, "paragraph_ms": 600, "lufs": -14.0}
CANDIDATES = [
    # A1: Indian-English accent = Hindi voices through the Hindi pipeline (baseline + English lines)
    ("a1-alpha", "Alpha (Indian English)", "Hindi voice hf_alpha reading the full set, incl. English lines", [("hf_alpha", 1)], {}),
    ("a1-beta", "Beta (Indian English)", "Hindi voice hf_beta reading the full set, incl. English lines", [("hf_beta", 1)], {}),
    ("a1-omega", "Omega (Indian English)", "Hindi voice hm_omega reading the full set, incl. English lines", [("hm_omega", 1)], {}),
    ("a1-psi", "Psi (Indian English)", "Hindi voice hm_psi reading the full set, incl. English lines", [("hm_psi", 1)], {}),
    # A2: blends (weighted average of style vectors), all through the Hindi pipeline
    ("a2-asha", "Asha", "Female · hf_alpha 50% + hf_beta 50%: between warm and bright", [("hf_alpha", .5), ("hf_beta", .5)], {}),
    ("a2-vikram", "Vikram", "Male · hm_omega 50% + hm_psi 50%: deep but steady", [("hm_omega", .5), ("hm_psi", .5)], {}),
    ("a2-meera", "Meera", "Female · hf_alpha 70% + af_heart 30%: warm, softer English", [("hf_alpha", .7), ("af_heart", .3)], {}),
    ("a2-kabir", "Kabir", "Male · hm_omega 70% + am_michael 30%: confident presenter", [("hm_omega", .7), ("am_michael", .3)], {}),
    ("a2-riya", "Riya", "Female · hf_beta 70% + bf_emma 30%: bright, polished", [("hf_beta", .7), ("bf_emma", .3)], {}),
    ("a2-arjun", "Arjun", "Male · hm_psi 70% + bm_george 30%: calm narrator", [("hm_psi", .7), ("bm_george", .3)], {}),
    ("a2-naina", "Naina", "Female · hf_beta 60% + af_bella 40%: expressive", [("hf_beta", .6), ("af_bella", .4)], {}),
    ("a2-dev", "Dev", "Male · hm_psi 60% + am_fenrir 40%: bold", [("hm_psi", .6), ("am_fenrir", .4)], {}),
    # A3: tone presets (no new model: speed + pauses + loudness)
    ("a3-energetic", "Energetic reel (Beta)", "Speed 1.12, short pauses (150 / 400 ms), -14 LUFS", [("hf_beta", 1)], {"speed": 1.12, "sentence_ms": 150, "paragraph_ms": 400}),
    ("a3-calm", "Calm narrator (Psi)", "Speed 0.92, longer pauses (400 / 900 ms), -16 LUFS", [("hm_psi", 1)], {"speed": 0.92, "sentence_ms": 400, "paragraph_ms": 900, "lufs": -16.0}),
    ("a3-announcer", "Ad announcer (Omega)", "Speed 1.05, crisp pauses (200 / 500 ms), -14 LUFS", [("hm_omega", 1)], {"speed": 1.05, "sentence_ms": 200, "paragraph_ms": 500}),
    ("a3-explainer", "Friendly explainer (Alpha)", "Speed 1.0, standard pauses (250 / 600 ms), -14 LUFS", [("hf_alpha", 1)], {}),
]


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    model = KModel(repo_id="hexgrad/Kokoro-82M").eval()
    pipe = KPipeline(lang_code="h", repo_id="hexgrad/Kokoro-82M", model=model)
    text = "\n\n".join(t for _, t in TEST_SET)
    paragraphs = split_text(normalize(text, "h"))
    manifest = []
    for cid, name, desc, spec, preset in CANDIDATES:
        p = DEFAULT | preset
        voice = sum(w * pipe.load_voice(v) for v, w in spec) / sum(w for _, w in spec)
        voice = voice.to(torch.float32)
        t0 = time.perf_counter()
        clips = []
        with torch.inference_mode():
            for para in paragraphs:
                row = []
                for s in para:
                    chunks = [r.audio.numpy() for r in pipe(s, voice=voice, speed=p["speed"], split_pattern=None) if r.audio is not None]
                    a = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
                    a = audio.trim_silence(a, SR, -45, keep_ms=20)
                    if a.size:
                        row.append(a)
                clips.append(row)
        joined = audio.join_segments(clips, SR, p["sentence_ms"], p["paragraph_ms"])
        joined = audio.pad_edges(audio.trim_silence(joined, SR, -45, keep_ms=20), SR, 80)
        synth = time.perf_counter() - t0
        loud = audio.export(joined, SR, out / cid, sample_rate=48000, mp3_bitrate="192k", target_lufs=p["lufs"],
                            true_peak=-1.0, compressor=audio.Compressor())
        (out / f"{cid}.wav").unlink(missing_ok=True)  # MP3 only on the preview page
        dur = len(joined) / SR
        row = {"id": cid, "track": cid[:2].upper(), "name": name, "description": desc,
               "voices": [{"voice": v, "weight": w} for v, w in spec], "preset": p,
               "duration_sec": round(dur, 1), "synth_sec": round(synth, 1), "rtf": round(synth / dur, 2),
               "peak_rss_mb": round(rss_mb()), "output_lufs": loud.output_lufs, "licence": "Apache-2.0 (Kokoro-82M)"}
        manifest.append(row)
        print(f"{cid:14} {dur:5.1f}s audio in {synth:5.1f}s (RTF {synth / dur:.2f}), peak RSS {rss_mb():.0f} MB", flush=True)
    (out / "manifest.json").write_text(json.dumps({"test_set": TEST_SET, "candidates": manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))

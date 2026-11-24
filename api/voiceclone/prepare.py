"""Precompute and cache a clone voice's tone colours (data/voices/<id>/tone_color.pt), then restart voice-clone.

    cd api && .venv/bin/python -m voiceclone.prepare --voice hi_reel_narrator_m1

target = OpenVoice reference encoder over the voice's reference clip (clip B for Veer).
source = the same encoder over ~1 minute of the Kokoro `source_voice` reading fixed Hindi scripts (as in the phase 13
lab, so the result matches what the owner approved). Loads Kokoro in this process for about a minute: needs ~2 GB free.
"""
import argparse
import sys
import time

import soundfile as sf

from settings import get_settings
from tts.clone_voices import load_clone_voices
from tts.text import normalize, split_text

from .worker import MODEL_NAME, file_sha256, mem_available_mb, tone_color_path

# Five Hindi scripts like the phase 13 lab set (api/scripts/custom_voice/common.py SCRIPTS): hook, Hinglish, numbers, reel, calm.
SOURCE_TEXTS = [
    "रुको! अगर तुम रोज़ जिम जाते हो और फिर भी बॉडी नहीं बन रही, तो गलती तुम्हारी मेहनत में नहीं, तुम्हारे प्लान में है। ये वीडियो पूरा देखना।",
    "आज का workout plan बहुत simple है। बस तीन exercises, पंद्रह minute, और zero excuses। Let's go!",
    "सिर्फ़ ₹499 में पूरे महीने का diet plan, और पहले 100 लोगों को 20% की छूट। ये ऑफ़र 31 दिसंबर तक है, और 2,500 से ज़्यादा लोग इसे पहले ही ले चुके हैं।",
    "सुबह उठते ही फ़ोन उठाते हो? तो ये आदत आज ही बदलो, क्योंकि तुम्हारे दिन का पहला घंटा ही पूरे दिन का मूड तय करता है। "
    "पहला काम: उठते ही एक गिलास पानी पियो। रात भर में बॉडी डिहाइड्रेट हो जाती है, और यही थकान की सबसे बड़ी वजह है। "
    "दूसरा: दस मिनट धूप में चलो। सुबह की रोशनी तुम्हारी बॉडी क्लॉक को सेट करती है, जिससे रात को नींद जल्दी और गहरी आती है।",
    "कभी-कभी सबसे बड़ा कदम बस रुककर एक गहरी साँस लेना होता है। धीरे चलो, पर रुको मत।",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True)
    args = ap.parse_args()
    s = get_settings()
    voices = load_clone_voices(s.data_dir / "voices")
    v = voices.get(args.voice)
    if v is None:
        print(f"no voice.json for {args.voice}", file=sys.stderr)
        return 1
    if (free := mem_available_mb()) < 2000:
        print(f"only {free} MB available; need ~2000 MB to load Kokoro here. Try when the server is quiet.", file=sys.stderr)
        return 2
    import numpy as np
    import torch
    torch.set_num_threads(s.torch_threads)
    from tts.kokoro_engine import KokoroEngine
    from .converter import ToneConverter

    t0 = time.perf_counter()
    conv = ToneConverter(s.data_dir / "models" / MODEL_NAME)
    conv.load()
    ref = s.data_dir / "voices" / v.id / v.reference_path
    a, sr = sf.read(ref, dtype="float32", always_2d=False)
    tgt = conv.embedding([(a if a.ndim == 1 else a.mean(axis=1), sr)])

    eng = KokoroEngine(s.torch_threads)
    eng.load()
    clips = []
    for text in SOURCE_TEXTS:
        parts = [eng.synthesize(sent, v.source_voice, v.lang, 1.1) for para in split_text(normalize(text, v.lang)) for sent in para]
        clips.append((np.concatenate([p for p in parts if p.size]), eng.sample_rate))
    src = conv.embedding(clips)
    out = tone_color_path(v)
    torch.save({"model": MODEL_NAME, "source_voice": v.source_voice, "reference_sha256": file_sha256(ref),
                "tgt_se": tgt, "src_se": src, "created": time.time()}, out)
    out.chmod(0o600)
    secs = sum(len(c) / c_sr for c, c_sr in clips)
    print(f"wrote {out} (source: {secs:.0f} s of {v.source_voice}) in {time.perf_counter() - t0:.0f}s. "
          f"Now: pm2 restart voice-clone")
    return 0


if __name__ == "__main__":
    sys.exit(main())

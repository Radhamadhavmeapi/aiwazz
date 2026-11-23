#!/usr/bin/env python3
"""Generate the voice preview samples with our own API (voice-api on 127.0.0.1:8100).

Writes landing/samples/<voice>.mp3, demo-*.mp3 and samples.json (used by landing + dashboard).
Usage: python3 tools/make_samples.py [--api http://127.0.0.1:8100]
"""
import argparse
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "landing" / "samples"

HI_F = "नमस्ते! मैं आपकी अगली रील के लिए वॉइसओवर तैयार कर सकती हूँ।"
HI_M = "नमस्ते! मैं आपकी अगली रील के लिए वॉइसओवर तैयार कर सकता हूँ।"
EN = "Hi, I'm {name}. I can voice your next reel in seconds."

DEMOS = {
    "demo-hi": ("hf_alpha", "रात ग्यारह बजे कस्टमर का फ़ोन आया। ऑर्डर अभी तक नहीं पहुँचा था। "
                            "हमने दस मिनट में वजह ढूँढी, और अगली सुबह पार्सल उसके दरवाज़े पर था।"),
    "demo-en": ("am_michael", "Most reels lose people in the first two seconds. "
                              "A clear, confident voice keeps them watching. Write your script, pick a voice, done."),
}


def post(api: str, body: dict) -> dict:
    req = urllib.request.Request(f"{api}/api/tts?wait=true", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def fetch(api: str, path: str, dest: Path) -> None:
    with urllib.request.urlopen(f"{api}{path}", timeout=60) as r:
        dest.write_bytes(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8100")
    api = ap.parse_args().api
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{api}/api/voices", timeout=10) as r:
        voices = json.load(r)["voices"]

    jobs = {}
    for v in voices:
        text = (HI_F if v["gender"] == "female" else HI_M) if v["lang"] == "h" else EN.format(name=v["name"])
        jobs[v["id"]] = (v["id"], text)
    jobs.update(DEMOS)

    manifest = {}
    for name, (voice, text) in jobs.items():
        d = post(api, {"text": text, "voice": voice, "format": "mp3"})
        if d.get("status") != "done":
            raise SystemExit(f"{name}: {d}")
        fetch(api, d["urls"]["mp3"], OUT / f"{name}.mp3")
        manifest[name] = {"voice": voice, "text": text, "duration_sec": d["duration_sec"],
                          "lufs": d["loudness"]["output_lufs"], "file": f"{name}.mp3"}
        print(f"{name:12} {d['duration_sec']:5.2f}s  {d['loudness']['output_lufs']} LUFS")
    (OUT / "samples.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

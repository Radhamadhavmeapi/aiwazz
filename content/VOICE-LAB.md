# Voice Lab: more Indian voices and tones (phase 10)

Goal: more Indian voices, Indian-English accents and Hinglish tones, **without hurting speed, RAM or licensing**.
This phase is research and samples only. **Nothing goes into the product until the owner approves the samples.**

## Hard limits (reject anything that fails)
- Licence must allow commercial SaaS use (Apache-2.0, MIT, CC-BY). Reject non-commercial (CC-BY-NC, research-only), unclear or "gated with extra terms" models unless the terms clearly allow commercial use. Record the licence URL for each.
- Runs on this CPU (AVX, no AVX2, 4 threads, 6 GB RAM, no swap) next to the running voice-api:
  peak RAM for the new engine ≤ 2.5 GB, speed ≤ 3× real time (60 s of audio in ≤ 180 s). Test `import` first: native wheels may crash with "Illegal instruction".
- Disk: keep total new downloads ≤ 6 GB; delete rejected models' files after testing (they're your own temp files).
- Never clone a real person's voice. No voice cloning features in this phase.

## Track A: new voices from Kokoro (cheap, try first)
1. **Indian-English accent:** Hindi voices (`hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi`) reading English text through the Hindi pipeline (`lang_code='h'`). Also English text inside Hindi sentences (Hinglish). Judge whether it sounds like natural Indian English.
2. **Voice blends:** Kokoro voices are style vectors that can be mixed (weighted average of voice tensors). Make 6–10 candidates, e.g. 70/30 and 50/50 mixes of the Hindi voices with each other and with English voices; keep ones that sound like a distinct, natural new person.
3. **Tone presets** (no new model): per-voice presets of speed + pause length + loudness, e.g. "Energetic reel" (1.12, short pauses), "Calm narrator" (0.92, longer pauses), "Ad announcer" (1.05). Name them in plain language.
Test text set (use for every candidate): 2 Hindi lines in Devanagari, 2 Hinglish lines (Devanagari + English words), 2 Indian-English lines, 1 line with numbers and ₹ prices.

## Track B: open Indian TTS models (only if they pass the limits)
Evaluate, in this order, and stop a candidate as soon as it fails a limit:
1. **ai4bharat/indic-parler-tts**: many Indian speakers, Indian-English, voice chosen by a text description. Check the HF gating terms for commercial use; measure CPU speed (it's ~0.9B params, may be too slow; try int8/ONNX if available).
2. **Other open Indian models found on Hugging Face** (e.g. svara-TTS, Maya 2 Native, IndicF5, Pocket TTS Hindi): check licence first, then speed/RAM.
For each: licence, voices/speakers available, Hindi/Hinglish/Indian-English quality, RTF, peak RAM, disk size, notes.

## Track C: paid API option (report only, no key, no code)
Summarise Sarvam Bulbul (Indian voices API, priced per 10k characters) as a possible "Premium Indian voices" tier: cost per 1,000 characters vs our plan prices, and what character multiplier (e.g. premium voices count 2×) would keep a healthy margin. Do not sign up or add keys.

## Output
- Samples (MP3, -14 LUFS, same post-processing as production) on a **hidden preview page** `https://login.aiwazz.in/preview/voice-lab/` with `noindex`, grouped by track, each with a name, description, licence and a 👍/👎 note field that is just client-side (no backend).
- Do not commit audio; generate it into the deployed preview folder.
- A report `content/VOICE-LAB-REPORT.md` (committed): table of every candidate (licence, quality notes, RTF, RAM, verdict) + recommendation of the final voice list (target: **8–12 Hindi/Indian voices** and **3–4 tone presets**) + effort to ship.
- Shipping into the product waits for owner approval.

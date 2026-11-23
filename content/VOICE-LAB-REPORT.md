# Voice Lab report (phase 10)

Run: 23–24 November 2026 (overnight). Samples: **https://login.aiwazz.in/preview/voice-lab/** (noindex, not in the product).
Every sample uses production post-processing (sentence split, trims, pauses, compressor + true-peak limiter,
-14 LUFS unless noted, MP3 48 kHz). Nothing has been added to the product; shipping waits for your approval.

**Important caveat:** I can't listen to audio. Everything below is measured (speed, RAM, licence, phonemes,
voice-vector distance); **sound quality is your call** on the preview page (👍/👎 and notes are saved in your browser).

## Test set (same for every candidate)
2 Hindi lines (Devanagari), 2 Hinglish lines (Devanagari + English words), 2 Indian-English lines,
1 line with ₹ and Indian-format numbers (`₹499`, `2,00,000`).

## Track A: Kokoro (Apache-2.0, already installed, no extra RAM or disk)

| ID | Candidate | What it is | RTF | Peak RAM* | Distinctness** | Verdict |
|---|---|---|---|---|---|---|
| a1-alpha … a1-psi | Hindi voices reading English | Indian-English accent via the Hindi pipeline | 0.80–0.86 | 1.5–1.9 GB | – | **Listen.** English words use espeak's English phonemes, so the "Indian" part comes from the voice timbre, not Indian-English pronunciation (retroflex t/d, syllable timing). espeak-ng here has no `en-in` variant. |
| a2-asha | Asha (F) | hf_alpha 50 + hf_beta 50 | 0.85 | 1.9 GB | 0.959 | Candidate |
| a2-vikram | Vikram (M) | hm_omega 50 + hm_psi 50 | 0.81 | 1.9 GB | 0.973 | Likely too close to Psi |
| a2-meera | Meera (F) | hf_alpha 70 + af_heart 30 | 0.88 | 1.9 GB | 0.971 | Likely too close to Alpha |
| a2-kabir | Kabir (M) | hm_omega 70 + am_michael 30 | 0.82 | 1.9 GB | 0.958 | Candidate |
| a2-riya | Riya (F) | hf_beta 70 + bf_emma 30 | 0.82 | 1.9 GB | 0.966 | Candidate |
| a2-arjun | Arjun (M) | hm_psi 70 + bm_george 30 | 0.81 | 1.9 GB | 0.949 | **Strong candidate** |
| a2-naina | Naina (F) | hf_beta 60 + af_bella 40 | 0.82 | 1.9 GB | 0.936 | **Strong candidate** |
| a2-dev | Dev (M) | hm_psi 60 + am_fenrir 40 | 0.78 | 1.9 GB | 0.911 | **Strong candidate** (most distinct) |
| a3-energetic | Energetic reel | Beta, speed 1.12, pauses 150/400 ms, -14 LUFS | 0.85 | – | – | Preset |
| a3-calm | Calm narrator | Psi, speed 0.92, pauses 400/900 ms, -16 LUFS | 0.76 | – | – | Preset |
| a3-announcer | Ad announcer | Omega, speed 1.05, pauses 200/500 ms, -14 LUFS | 0.80 | – | – | Preset |
| a3-explainer | Friendly explainer | Alpha, speed 1.0, pauses 250/600 ms, -14 LUFS | 0.81 | – | – | Preset |

\* Peak RSS of the whole test process including the shared Kokoro model (production voice-api uses ~1.7 GB). Blends add no RAM.
\** Cosine similarity of the voice vector to the nearest existing Hindi voice (1.0 = identical). For reference, the existing
voices differ from each other at 0.83 (Alpha/Beta) and 0.89 (Omega/Psi); lower = more distinct new speaker.

All Track A candidates pass every limit (licence Apache-2.0; RTF < 1 vs limit 3; RAM < 2.5 GB; 0 extra disk).

**Bug found and fixed in production while testing:** `₹` was silently dropped and Indian-format numbers (`2,00,000`) were read
digit by digit. Production now says "499 रुपये" / "499 rupees", reads 2,00,000 as "दो लाख", and Hindi decimals with
"दशमलव" (`api/tts/text.py: normalize`, tested). The samples on the preview page were regenerated with the fix.

## Track B: open Indian TTS models

| Model | Licence | Size | Verdict |
|---|---|---|---|
| ai4bharat/indic-parler-tts (+ pretrained) | Apache-2.0, gated (auto) | 0.94 B params, 3.75 GB fp32 | **FAIL** RAM (weights alone > 2.5 GB); speed very likely fails |
| ai4bharat/IndicF5 | MIT, gated (auto) | 0.35 B, 1.4 GB | **FAIL** cloning-only (needs consented reference), no English, speed unlikely |
| kenpath/svara-tts-v1 | Apache-2.0 card, Llama-3.2 base (unclear) | 3.3 B, 13 GB | **FAIL** RAM, speed, licence unclear |
| maya-research/Veena | Apache-2.0 | 3.8 B, 7.6 GB | **FAIL** RAM, speed (GPU only) |
| maya-research/maya2-native | Apache-2.0 | 2.5 B, 5 GB | **FAIL** needs NVIDIA GPU |
| facebook/mms-tts-hin | CC-BY-NC-4.0 | 36 M | **FAIL** non-commercial |
| rhasspy/piper-voices hi_IN | MIT code; datasets: pratham/priyamvada CC BY-NC-SA, rohan IITM licence (unverified) | 63 MB | **FAIL** (NC) / rohan **unknown licence** |
| saryps-labs/pocket-tts-hindi | CC BY 4.0 | 110 M (int8 ONNX 240 MB) | **Owner decision.** Publishes 3.4–3.7× real time on 1 modern thread, 1.2–1.3 GB RAM. But it only clones from a reference clip (we'd need a consenting speaker), Hindi only, early research release. |
| altslate/jugnu-pocket-tts | CC BY 4.0, gated (auto, + kyutai gate) | 89–165 M | **Owner decision.** Hindi + Hinglish, cloning only, research preview, gated download (needs a Hugging Face account), speed unknown on this CPU. |
| bodhan-ai/indic-speak | custom "Indic Open Model License", gated | 3.3 B | **FAIL** custom licence, too big |

No model was downloaded: every named candidate failed a hard limit on paper, and the two that might fit need a consenting
voice speaker (cloning was out of scope tonight) and/or a gated download. Disk used by Voice Lab: 0 GB of models, ~16 MB of samples.

Sources: model cards and `huggingface.co/api/models/<repo>` for each repo above (checked 23 Nov 2026).

## Track C: paid API (report only, no account, no key)

**Sarvam Bulbul** (sarvam.ai/api-pricing, docs.sarvam.ai): `bulbul:v4-flash` ₹20 per 10,000 characters (₹2 / 1,000),
`bulbul:v3` ₹30 per 10,000; 200+ personas incl. Hindi-English code-mixed, `en-IN`; up to 48 kHz; 2,500 characters per
request; ₹100 free credits.

Our revenue per 1,000 plan characters (excl. GST): Starter ₹3.98, Creator ₹2.50, Pro ₹2.00.
At 1× a premium voice costs ₹2 / 1,000, i.e. ~100% of Pro's revenue. With a **3× character multiplier** for premium voices:
Pro ₹6.00 → 67% gross margin, Creator ₹7.50 → 73%, Starter ₹11.94 → 83%.

**Blocker:** Sarvam's Terms (§9) prohibit reselling or offering the API "on a hosted-service basis" to third parties and
building competing products without written permission. A written reseller agreement is required before any
"Premium Indian voices" tier. Using it for your own reels is fine.

## Recommendation

**Voices (10, target 8–12):** keep the 4 current Hindi voices (Alpha, Beta, Omega, Psi) and add 6 blends, subject to your
listening: **Dev, Naina, Arjun** (most distinct), then **Kabir, Asha, Riya**. Drop Vikram and Meera unless you hear a clear
difference. Present the Hindi voices also as "Indian English" options (they read English with an Indian timbre) only if
you like how a1-* sound.

**Tone presets (4):** Energetic reel, Calm narrator, Ad announcer, Friendly explainer (settings above).

**Not now:** open Indian models (all fail CPU/RAM/licence, or need a consenting speaker); Sarvam (needs a reseller agreement).

## Effort to ship (after your approval)

| Item | Effort |
|---|---|
| Blends as new voices (voice id → weights in `tts/voices.py`, load once at startup) | ~1–2 h incl. tests, samples, docs |
| Tone presets (API field `preset` + dashboard chips; pauses per request) | ~2–3 h |
| Landing/Learn/voice counts ("14 voices" → new number) | ~1 h |
| Pocket-TTS Hindi (needs a consented speaker recording + benchmark + new engine) | 1–2 days, plus consent paperwork |
| Sarvam premium tier | after a reseller agreement: ~1 day (engine adapter, multiplier, billing) |

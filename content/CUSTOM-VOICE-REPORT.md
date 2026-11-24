# Custom voice: Step 1 report (Veer, Energetic Reel (Hindi), `hi_reel_narrator_m1`)

24 Nov 2026 · brief: `content/CUSTOM-VOICE.md` · status: **samples ready, waiting for the owner's pick** (Steps 2–4 not started).

**Listen:** https://login.aiwazz.in/api/preview/custom-voice/ (sign in as admin first; everyone else gets 404;
`X-Robots-Tag: noindex`, `Cache-Control: private, no-store`). 10 candidates × 5 scripts = 50 samples + the two
narrator clips. 👍/👎 + notes stay in your browser; "Copy my picks" gives a text to paste back.

## 1. Server

| | |
|---|---|
| CPU | Xeon E5-2697 v2 (Ivy Bridge), 4 threads, **AVX + F16C, no AVX2** (torch: `cpu_capability NO AVX`, no NNPACK) |
| RAM | OpenVZ physpages 6 GB, no swap, `vm.overcommit_memory=1`; ≈3.1–3.5 GB available with voice-api (RSS ≈1.7 GB) running |
| OpenVZ quirk | a private (copy-on-write) `mmap` of a 2 GB weights file fails with ENOMEM; read-only shared mmap works |
| Disk | 9.9 GB free at the start → **2.2 GB free now (93 % full)**; see §8 |
| Threads | torch defaults to 1 thread here: every engine must call `torch.set_num_threads(4)` |

Safety: every test ran in its own process (nice 10–19) with a watchdog that exits if MemAvailable < 600 MB. It fired twice
(route C first attempts, see §4) and killed only the test; voice-api never swapped, restarted or failed a job.

## 2. Voice pack and source record

- `data/voices/hi_reel_narrator_m1/` (gitignored, dir 700 / files 600): `voice_reference_A_13s.wav` (12.8 s),
  `voice_reference_B_16s.wav` (15.7 s), `voice_clean_full.wav` (67.6 s), `transcripts.txt`; all mono 44.1 kHz 16-bit.
- Source record (for Step 3): `source_type = ai_voice`, attested by the owner, `is_public = false`.
- ⚠️ **Mismatch to resolve before Step 3:** `transcripts.txt` says *"Consent: voice owner has agreed to its use on AiWazz
  (confirmed by the account owner). Keep the signed consent on file."* and *"Source: uploaded reel cdd8b84e-679099.mp4"*.
  That reads like a real person's voice taken from a reel, not an AI-generated voice. Please confirm which is true. If a
  real person is behind it, we need their signed consent on file and `source_type = consented_person`, not `ai_voice`.

## 3. Routes tested

| Route | What | Licence | Tested |
|---|---|---|---|
| Baseline | stock Kokoro `hm_omega` / `hm_psi` (today's voices) | Apache-2.0 | ✔ |
| **A** | Kokoro (speed 1.1, calm 1.0) → **OpenVoice v2 tone colour converter**, tau 0.3, target from clip A or B | MIT, [myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice) (watermark off) | ✔ 4 variants |
| **B** | **Chatterbox Multilingual** (`language_id="hi"`, exaggeration 0.5), zero-shot from clip A or B | MIT, [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) (Perth watermark on by default) | ✔ 2 variants |
| B2 | IndicF5 | gated on Hugging Face (needs an account token; this server has none); licence not verified | ✘ |
| **C\*** | Kokoro → **kNN-VC** (WavLM-Large features matched against the narrator's own audio, HiFiGAN vocoder); no training | MIT, [bshall/knn-vc](https://github.com/bshall/knn-vc); WavLM MIT ([microsoft/unilm](https://github.com/microsoft/unilm)) | ✔ 3 variants (A, B, full 67 s) |
| C | RVC trained on Colab/Kaggle | needs a one-time training run in your Google/Kaggle account | ✘ (see §7) |

Not used: XTTS-v2 (CPML, non-commercial) and every other non-commercial model.
Metrics: faster-whisper small (int8, hi, beam 5), MIT ([SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper));
speaker similarity = Chatterbox VoiceEncoder cosine against the full clean clip.

Scripts (identical for every route): 1 hook · 2 Hinglish · 3 numbers/₹ · 4 full 60 s reel · 5 calm.
Output post-processing is the production chain (trim, pauses, -14 LUFS / -1 dBTP, 48 kHz).

## 4. Results

**Calibration:** the narrator's clips score **98 %** similarity against each other (A~B 0.976, A~full 0.991); Whisper reads
the narrator's own clips at CER 14.7 % (A) / 8.6 % (B). So ~98 % is "same voice", and ~10–15 % CER is "human-clear" for
this Whisper size on Hindi.

| Candidate | Similarity | CER (avg of 5) | Hinglish CER | Speed (compute ÷ audio) | 60 s reel | Extra RAM | Load |
|---|---|---|---|---|---|---|---|
| Kokoro Omega (today) | 77 % | 13 % | 25 % | 0.85× | ≈50 s | 0 (loaded) | – |
| Kokoro Psi (today) | 71 % | 13 % | 26 % | 0.85× | ≈50 s | 0 | – |
| A · Omega → clip A | 85 % | 18 % | 25 % | 1.75× | ≈1.7 min | 131 MB weights; peak RSS 2.2 GB (whole-file conversion, chunking lowers it) | 1 s |
| A · Omega → clip B | 84 % | 18 % | 26 % | 1.76× | ≈1.8 min | 〃 | 1 s |
| A · Psi → clip A | 86 % | 19 % | 29 % | 1.74× | ≈1.7 min | 〃 | 1 s |
| **A · Psi → clip B** | 85 % | **15 %** | 25 % | 1.72× | ≈1.7 min | 〃 | 1 s |
| B · Chatterbox, clip A | **94 %** | 23 % (numbers 48 %) | 21 % | **28–64×** | **≈28–74 min** | +3.0–3.4 GB RSS (min free 0.8 GB) | 23–37 s |
| B · Chatterbox, clip B | 93 % | 17 % | 23 % | 61–67× | ≈74 min | 〃 | 23–37 s |
| C · kNN-VC, clip A | 90 % | 19 % | 36 % | 1.6× | ≈1.6 min | 1.3 GB weights; peak RSS 2.3 GB | 3 s (cached) |
| C · kNN-VC, clip B | 90 % | 18 % | 27 % | 1.6× | ≈1.6 min | 〃 | 3 s |
| **C · kNN-VC, full 67 s** | **92 %** | 19 % | 27 % | 1.6× | ≈1.6 min | 〃 | 3 s |

Notes:
- **Chatterbox (B) is the closest voice but unusable on this CPU.** The first test ran at RTF 28 (no other load); the full
  set at nice 19 alongside the live API ran at RTF 58–67. The 60 s reel took 72–74 minutes. It also speaks slower (the
  "60 s" reel came out 70–73 s), it logged "forcing EOS / token repetition" on most long sentences, and on the numbers
  script with clip A it **hallucinated a nonsense tail** after the last sentence (CER 48 %). Hinglish English words are
  read with a Hindi accent ("वर्कोट प्लन", "जेरो एकस्कुसिस").
- **Route A** keeps Kokoro's clarity and timing; the converter mostly moves the timbre. Small weights (131 MB) and fast; its 2.2 GB peak came from converting whole files at once, so production should convert per sentence.
  It is still noticeably "Kokoro-shaped" (85 %).
- **Route C (kNN-VC)** gets much closer (90–92 %) at the same cost as A, because it rebuilds every frame from the narrator's
  own audio. More reference audio helps (full 67 s > 16 s clips). Listen for artefacts: with only about 1 minute of target
  audio, kNN-VC can sound slightly smeared or metallic on sounds the narrator never says in the clip. First attempts
  ran out of memory: WavLM attention and HiFiGAN both grow with clip length. Fixed by feeding WavLM ≤ 10 s chunks and
  vocoding in 10 s windows with crossfades, and by loading the 1.26 GB checkpoint only once (meta-device + assign).
- Hinglish CER is high for every route, including stock Kokoro: Whisper-small struggles with English words in Hindi
  audio. Use the Hinglish column to compare routes, not as an absolute score.

**Kokoro while tests ran** (live API, the same 11 s Hindi sentence, compute seconds):

| | idle | during Chatterbox | during kNN-VC | during OpenVoice | after all tests |
|---|---|---|---|---|---|
| compute for 11.0 s audio | 11.6–11.8 s | 13.1–14.7 s (+15–25 %) | 12.0–14.1 s (+3–20 %) | (not measured separately; the conversion phase is the same CPU load as kNN-VC) | **11.4–12.2 s (normal)** |

So a clone engine running next to Kokoro slows Kokoro jobs by up to about 25 % while it computes, and nothing else. In
production the clone step would run inside the same one-at-a-time queue, so it never overlaps a Kokoro job.

## 5. Recommendation

1. **Listen first to `C · kNN-VC, full 67 s` and `A · Psi → clip B`** (and `B · Chatterbox, clip B` to hear the ceiling).
2. If C-full sounds clean to you, **ship route C (Kokoro → kNN-VC, matching set = the full clean clip)**. It is the closest
   voice we can run on this CPU (92 % vs 85 % for A) at the same speed (60 s reel ≈ 1.6 min). The cost is +1.3 GB RAM
   while it is loaded, so load it on demand per job and unload it after an idle timeout. Kokoro + WavLM ≈ 3 GB of the
   6 GB stays inside the safe margin.
3. If C sounds artefacty, **ship route A with Psi → clip B**: the clearest result (CER 15 %, the same as stock Kokoro),
   lightest (131 MB of weights, 1 s load), and 85 % similar.
4. **Clip choice: B.** It is the cleaner recording (Whisper CER 8.6 % vs 14.7 %), and it gave the clearer output on
   routes A and B with the same similarity. For route C, use the full 67 s clip (clip B on its own is the fallback).
5. Chatterbox: reject on this server (an hour per reel). Revisit only with a GPU.
6. RVC (route C proper): not needed unless both C-full and A disappoint. It needs one Colab/Kaggle training run that you
   start in your own account.

## 6. GPU and pricing notes

- On a rented GPU, Chatterbox would be the obvious choice (94 % similarity, natural prosody). Speed was not measured here,
  since there is no GPU, but it is expected to be far faster than realtime. That is the "rented GPU" item in CLAUDE.md
  → Later.
- On CPU, the clone routes cost about 2× the compute of a stock Kokoro job (1.6–1.75× vs 0.85×). If custom or studio voices
  are ever offered to customers, count them at about 2× characters or price them higher. For now the voice is owner-only.

## 7. What was installed (all outside the repo, no audio in git)

| | Size | Keep? |
|---|---|---|
| `/root/voicelab/venv` (torch 2.6 CPU, chatterbox-tts, faster-whisper, …) | 2.0 GB | until the pick |
| OpenVoice v2 converter `models/openvoice` | 126 MB | route A |
| Chatterbox Multilingual `models/chatterbox` | 3.0 GB | **delete after the pick** (rejected for CPU) |
| WavLM-Large + kNN-VC HiFiGAN `~/.cache/torch/hub/checkpoints` | 1.3 GB | route C |
| faster-whisper small `models/whisper-small` | 464 MB | QA tool |
| `~/.pkuseg` (Chatterbox tokenizer data, pulled in automatically) | 91 MB | delete with Chatterbox |
| total new downloads | ≈7.0 GB | ≤ 8 GB budget |

Rejected models are kept until you have listened, in case you want a re-run. Say "pick X" and I delete the rest (Chatterbox
alone frees 3.1 GB, which also fixes the 93 % disk).

Lab code (reproducible): `api/scripts/custom_voice/` (`common.py`, `kokoro_gen.py`, `route_a.py`, `route_b.py`,
`route_c.py`, `evaluate.py`, `make_page.py`); outputs in `/root/voicelab/out/`; page + MP3s in
`data/voices/hi_reel_narrator_m1/lab/` (served only through `GET /api/preview/custom-voice/…`, admin session only).

## 8. Other findings

- **`https://login.aiwazz.in/preview/voice-lab/` (phase 10 samples) is publicly reachable** (200 without login). It is
  noindex and the URL is unlisted, but anyone with the link can listen. It could move behind the same admin-only
  `/api/preview/` route; say if you want that.
- Disk is at 93 % (2.2 GB free). Deleting Chatterbox after the pick brings it back to ≈5.3 GB.

## 9. Next (waiting for the owner)

Your pick (route + clip) → Step 2 (engine wiring), Step 3 (`voice_consents` record with the source attestation, after the
§2 mismatch is resolved), Step 4 (owner-only voice in Generate). Nothing of that has been started.

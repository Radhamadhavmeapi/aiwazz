# Custom voice report (Veer, Energetic Reel (Hindi), `hi_reel_narrator_m1`)

24 Nov 2026 · brief: `content/CUSTOM-VOICE.md` · status: **Steps 1–4 done. Veer works in Generate and the API for the owner
account only (`is_public = false`).** Making it public is a separate owner decision.

**Listen:** https://login.aiwazz.in/api/preview/custom-voice/ (sign in as admin first; everyone else gets 404;
`X-Robots-Tag: noindex`, `Cache-Control: private, no-store`). The top section has the 3 real reels made through the live
app (Step 4); below it are the Step 1 route comparisons (the Psi variants were deleted after the pick).

**Owner decision (24 Nov 2026):** ship **route A = Kokoro `hm_omega` → OpenVoice v2 tone colour conversion, reference
clip B**. Ratings: A·Omega→B 👍 on Hinglish, numbers, full reel and calm; A·Omega→A 👎 on the hook; A·Psi 👎 on the full
reel; Chatterbox good but too slow; route C not rated.

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
- Source record: `voice_consents` #1, `source_type = ai_voice`, status `active`, added by the owner's admin account:
  "Owner states the reference is an AI-generated voice, not a real person (24 Nov 2026). Owner-only (is_public = false)."
- Resolved: the consent line in `transcripts.txt` was template text (owner, 24 Nov 2026). It now records the AI-voice
  attestation. The "Source: uploaded reel" line stays: the AI voice's audio was taken from that reel.

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

| | Size | Status (24 Nov 2026, after the pick) |
|---|---|---|
| OpenVoice v2 converter → **`data/models/openvoice_v2/`** | 126 MB | **production** (voice-clone worker) |
| `/root/voicelab/venv` (lab only: torch 2.6 CPU, faster-whisper, librosa) | 1.8 GB | kept for QA (CER + similarity) |
| faster-whisper small `models/whisper-small` + speaker encoder `models/ve` (5.7 MB, vendored MIT code in `ve/`) | 470 MB | kept for QA |
| Chatterbox weights, its pip packages (chatterbox-tts, s3tokenizer, perth, conformer, diffusers, transformers, …), `~/.pkuseg` | 3.3 GB | **deleted** (its 10 samples stay on the page) |
| Psi test outputs (Kokoro Psi, route A Psi→A/B) | ~30 MB | **deleted** |
| WavLM-Large + kNN-VC HiFiGAN, `knnvc/`, route C outputs + samples | 1.3 GB | **auto-delete 25 Nov 2026 23:30 IST** (`at` job 1, `/root/voicelab/delete_route_c.sh`; keep with `touch /root/voicelab/KEEP_ROUTE_C`) |

Disk: 2.2 GB free → **5.5 GB free (81 %)** now; ≈6.8 GB after route C goes. The API venv gained only `soxr` (1 package).

Lab code (reproducible): `api/scripts/custom_voice/` (`common.py`, `kokoro_gen.py`, `route_a.py`, `route_b.py`,
`route_c.py`, `evaluate.py`, `make_page.py`); outputs in `/root/voicelab/out/`; page + MP3s in
`data/voices/hi_reel_narrator_m1/lab/` (served only through `GET /api/preview/custom-voice/…`, admin session only).

## 8. Other findings

- Fixed: the phase 10 Voice Lab page moved out of the web root to `data/preview/voice-lab/` and is now served only at
  **https://login.aiwazz.in/api/preview/voice-lab/** (admin session, noindex; 404 for everyone else). The old
  `/preview/voice-lab/` URL only shows the app now.

## 9. Steps 2–4: how Veer runs

```
Generate / POST /api/tts {"voice": "hi_reel_narrator_m1"}           (owner account only; consent record must be active)
  → Kokoro queue (shared, one at a time): Kokoro hm_omega reads the script, sentence by sentence
  → clone queue (separate, one at a time): each sentence → voice-clone worker → OpenVoice v2 (clip B tone colour)
  → the usual post-processing: trim, pauses, -14 LUFS / -1 dBTP, WAV + MP3 48 kHz → History, 7-day cleanup
```

- **Worker** `voice-clone` (PM2, `api/voiceclone/worker.py`): 127.0.0.1:8101 only, `X-Clone-Secret` (random, in
  `api/.env` only), `nice -n 10`, 3 torch threads, ~540 MB RSS, `max_memory_restart` 1.5 GB. The model stays loaded (it's
  small). Tone colours are computed once by `python -m voiceclone.prepare` and cached in `tone_color.pt`; the source
  colour matches the lab's at cosine 0.991.
- **Interface:** the brief suggested `POST /synthesize {text, voice_id, speed}`. Route A needs Kokoro first, and a second
  Kokoro inside the worker would cost another 1.3 GB RAM we don't have. So the API's shared Kokoro reads the script, and the
  worker exposes `POST /convert` (WAV in → WAV out). A GPU worker for a direct-cloning engine (Chatterbox) can add
  `/synthesize` behind the same secret and URL (`AIWAZZ_CLONE_URL`).
- **Kokoro never waits for a conversion.** Conversions run in their own queue. A clone job's *speech* stage takes a normal
  turn in the Kokoro queue, the same as any job. While a conversion runs, both share the 4 CPUs: a short Kokoro job took
  6.2 s of compute for 4.5 s of audio (1.38×), against ≈1.05× when idle (measured on an 11 s sentence).
- **API:** `GET /api/voices` lists Veer (`engine: "clone"`, `tier: "studio"`, `is_public: false`) only to admins;
  `POST /api/tts` works unchanged with `"voice": "hi_reel_narrator_m1"`. With no style or speed given, it uses Energetic
  reel at **1.08×**; an explicit style or speed wins. Limit: **1,500 characters** per job. The job status adds `stage`
  (speech → studio-queue → studio) and `estimate_sec`. If the worker is down, the API answers 503 before anything runs.
  If it fails mid-job, the conversion is retried once, then the job ends in `error` with no characters charged.
- **Dashboard:** Veer appears in Generate and Voices with a "Studio" badge and a private preview
  (`/api/voices/{id}/preview`). Picking Veer sets Energetic reel at 1.08×. The editor shows the 1,500 limit and
  "about N to make", the progress panel shows "Converting to the studio voice", and History shows the name.

### Step 4 test (live API, temporary admin test account, deleted afterwards)

| Reel script | Characters | Audio | Compute | Speech / conversion / post | Loudness |
|---|---|---|---|---|---|
| Owner's reel: desi pre-workout shot (the narrator's own script) | 1,181 | 91.6 s | 227 s (2.48×) | 80 / 138 / 9 s | -14.2 LUFS, -1.3 dBTP |
| AiWazz promo in Roman Hinglish (transliterate on) | 331 | 23.2 s | 60 s (2.58×) | 35 / 22 / 3 s | -14.1 LUFS, -1.3 dBTP |
| Offer with ₹ and numbers | 215 | 19.2 s | 48 s (2.51×) | 27 / 18 / 3 s | -14.2 LUFS, -1.3 dBTP |

The three were submitted together, so their stages overlapped. A later job that ran mostly alone (215 characters) took 2.35×.

- Queue and progress: positions, stages and progress were reported correctly. MP3 (audio/mpeg) and WAV (audio/wav)
  downloaded for all three.
- Characters: +302 for 302 characters of successful jobs. The worker was stopped during a conversion: one retry, then
  "The studio voice is unavailable right now. Nothing was charged…", **0 characters charged**. A new Veer job while the
  worker was down got a 503 at once.
- 7-day cleanup: clone outputs are written to the same `storage/audio/` as every other job, so the hourly retention sweep
  removes them on the same schedule.
- **Speed note for you:** at 1.08× Veer reads your 67 s reel in 92 s. Kokoro's rhythm is slower than the original
  narrator. If you want reel pace, try 1.15–1.25× on the speed slider. The style default stays 1.08×, as you asked
  (1.05–1.10).
- Estimate shown in the app: ≈2.4× realtime ("a 60-second reel ≈ 2½ minutes"), measured, not guessed.

## 10. Still owner decisions

- Making Veer public (then: a Learn guide, the voices page, and whether studio voices count at about 2.5× characters or
  sit on a higher plan).
- Route C files go tomorrow night unless you say "keep route C".

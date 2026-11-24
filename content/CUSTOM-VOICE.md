# Custom voice brief: add the "Hindi reel narrator" voice to AiWazz (phase 13)

## Goal
Add one cloned studio voice, an energetic Hindi male reel narrator, so the owner can use it for many reels through the normal AiWazz web app and API. Build it so more consented voices can be added the same way later.

Kokoro (the current engine) cannot clone voices. This phase adds a way to produce this voice **on the existing VPS, CPU only**: no GPU and no paid services for now. A GPU comes later, once there's enough load, so design the engine so it can move to a GPU worker without changing the API.

Expect the CPU to be slow. The job is to find the option that sounds close enough **and** runs at a usable speed on this server, and to report the numbers honestly.

## Ground rules (in addition to CLAUDE.md)
- **Consent / source:** the owner states (24 Nov 2026) that this narrator is an **AI-generated voice, not a real person**. Record that as a source attestation (see "Consent record", `source_type = ai_voice`, attested by the owner) before the voice can be selected. Never add a voice without a record.
- **Owner-only until the source is cleared:** many commercial AI voices are themselves licensed from real voice actors, and the reference audio comes from someone else's reel. So this voice stays `is_public = false` (owner account only). Making it public needs a separate owner decision plus a note in the record naming the original tool/licence.
- **Nothing goes live without owner approval.** Build and test on a hidden preview page first.
- **No audio in git.** Voice files live on the server under `data/voices/` (gitignored).
- **Secrets** (GPU provider token, worker secret) go in `.env` only.
- **No paid services.** Free Colab or Kaggle is allowed only for a one-time training step (route C), never to serve requests.
- **Protect the live service:** Kokoro jobs must keep working. Check free RAM before loading any new model, and stop if it would push the server into swap.

## Inputs: the voice pack
The owner uploads `aiwazz_voice_pack.zip` to `/root/aiwazz_voice_pack.zip` (aaPanel → Files). Never commit it. It contains:

| File | Use |
|---|---|
| `voice_reference_A_13s.wav` | main reference clip (music removed, -16 LUFS, mono 44.1 kHz) |
| `voice_reference_B_16s.wav` | backup reference clip |
| `voice_clean_full.wav` | full 67 s narration, for fine-tuning later |
| `transcripts.txt` | exact Hindi (Devanagari) text of each clip |

Unzip to `data/voices/hi_reel_narrator_m1/` on the server (gitignored, chmod 700), then check the 4 files (A 12.8 s, B 15.65 s, full 67.5 s, all mono 44.1 kHz).

## Step 1: choose the CPU route (report, then wait for approval)
First record the server's CPU model, cores, AVX/AVX2 support, free RAM and disk, and whether OpenVZ limits anything (for example memory accounting or the thread count PyTorch sees).

Then test these routes **on the VPS CPU**, cheapest first:

- **A. Kokoro + voice conversion (fast, recommended first try).** Generate with the closest Kokoro Hindi male voice, then convert the timbre to the narrator using **OpenVoice v2's tone colour converter** (MIT licence; confirm on the official repo) with reference clip A. Conversion is light and should run near real time on CPU. Expect the right voice colour but Kokoro's rhythm, so test whether it sounds "energetic" enough; try Kokoro speed 1.05–1.15.
- **B. Direct zero-shot cloning on CPU.** **Chatterbox Multilingual** (confirm Hindi support and the MIT licence) and **IndicF5** (use only if its weights' licence allows commercial use). These sound most like the narrator but may be many times slower than real time on CPU. Measure, and drop any that need more RAM than the server can spare.
- **C. Trained voice-conversion model (only if A isn't close enough).** Train an RVC-style model once on free Colab or Kaggle using `voice_clean_full.wav` (only 67 s, so quality may be limited; say so), then run it on the CPU after Kokoro like route A. Use only code and pretrained bases whose licence allows commercial use.

**Do not use** XTTS-v2 (its Coqui Public Model License doesn't allow commercial use) or any model with a non-commercial licence.

For speed, report the **real-time factor** (seconds of compute per second of audio) and the time for a full 60-second reel. As a guide, under 1× is great, 1–3× is fine for a queued owner-only voice, and over 5× is too slow to offer to users.

For each candidate, generate the same 5 test scripts with reference clip A, then with clip B:
- one pure Hindi reel hook
- one Hinglish line (for example "आज का workout plan बहुत simple है")
- one with numbers and ₹ amounts
- one 60-second full reel script
- one calm or slow line, to see whether the voice stays the same person

Measure and write in `content/CUSTOM-VOICE-REPORT.md`:
- licence (with link), Hindi and Hinglish quality notes, similarity to the reference (owner listens), real-time factor on this CPU, peak RAM, model load time, disk space
- **Intelligibility check:** run each output through faster-whisper (`small`, `language="hi"`) and report the character error rate against the input text
- whether Kokoro slows down while the new engine runs
- a recommendation, with clip A or B chosen as the reference, plus a rough note on what a GPU would improve later

Put the samples on a hidden preview page (for example `/voice-lab/custom/`, behind login and `noindex`) so the owner can listen on his phone. **Stop and wait for the owner to pick.**

## Step 2: CPU worker on the VPS
- Run the chosen engine as its **own PM2 process** (for example `voice-clone`, on 127.0.0.1 only), separate from the main API, so a crash or memory spike doesn't take Kokoro down.
- Worker API: `POST /synthesize` with `{text, voice_id, speed}`, returns WAV. Protect it with a shared secret header. This same interface lets it move to a GPU host later by changing one URL in `.env`.
- **One clone job at a time**, in its own queue, so clone jobs never block Kokoro jobs. Run the worker at lower CPU priority (`nice`) and cap its threads so Kokoro stays responsive.
- Load the model once and keep it in memory only if RAM allows; otherwise load on demand and say what that costs in time.
- Pre-compute and cache the speaker embedding or tone colour from the reference clip, rather than recomputing it for each request.
- Split long text by sentence (same as the Kokoro path), synthesize, then join with the existing pause rules.
- Show an honest time estimate in the UI for clone jobs (for example "about 2 minutes"), based on the measured speed.
- If the worker fails, retry once, then mark the job `error` (no characters charged, per the existing rule).

## Step 3: wire it into AiWazz
- Add an engine type `clone` beside `kokoro`. Voices table or config gets: `id`, `name`, `engine`, `language`, `gender`, `tags`, `reference_path`, `reference_text`, `consent_id`, `is_public`, `tier` (for example `studio`).
- New voice: `id = hi_reel_narrator_m1`, display name **"Veer, Energetic Reel (Hindi)"** (owner can rename), tags `energetic, reels, fitness`.
- `GET /api/voices` lists it with `engine: "clone"`. `POST /api/tts` works unchanged with `"voice": "hi_reel_narrator_m1"`.
- The existing loudness pipeline (`normalize`, `loudness_lufs`, true peak below -1 dBTP) runs on clone output too.
- Start with `is_public = false`, so only the owner's account can use it. Opening it to other users is a separate owner decision.
- Add a per-request limit for clone jobs if the CPU is slow (for example 1,500 characters), and say so in the UI.
- Pricing: no change for now. Note in the report whether studio voices should cost more later, once they run on a GPU.

## Consent record
Table `voice_consents`: `id`, `voice_id`, `source_type` (`real_person` | `ai_voice`), `speaker_name` (or tool name if known), `consent_scope` (commercial use on AiWazz, reels and ads), `signed_document_path` (required for `real_person`, stored privately on the server), `attestation_note`, `date`, `added_by`, `revoked_at`.
For `hi_reel_narrator_m1`: `source_type = ai_voice`, attestation "Owner states the reference is an AI-generated voice (24 Nov 2026)", no signed document required for private use; status `active`, `is_public = false`.
- A voice can't be selected unless it has a consent record that isn't revoked.
- If consent is revoked, disable the voice immediately and delete its reference files and cached embedding.
- For `real_person` voices: ask the owner to upload the signed consent document; until then, mark the record `pending` and keep the voice hidden.

## Step 4: test and hand over
- Generate 3 real reel scripts from the owner's content with the new voice and add them to the preview page.
- Check: queue position and progress bar work, MP3 and WAV downloads work, character deduction is correct, failed jobs aren't charged, and the 7-day cleanup includes clone outputs.
- Update `/learn/` only if the voice becomes public (owner decision).
- Commit code and the report and push. Then **ask the owner for approval** before enabling the voice outside the preview page.

## Later (don't build yet)
- When load justifies it: move `voice-clone` to a GPU worker or a GPU server (same API), and switch to the best-sounding route from Step 1 if CPU limits forced a weaker one.
- Fine-tune on `voice_clean_full.wav`, plus more recordings of the same narrator, for a closer, steadier voice.
- A "Custom voice" feature for customers: upload a clip with a consent form, require a spoken verification phrase from the speaker, run abuse checks and label AI-generated audio according to current Indian rules.

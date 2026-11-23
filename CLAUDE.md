# AiWazz Voice — text-to-speech platform

A TTS platform for making voiceovers for short videos (Instagram reels, 9:16, Hinglish/Hindi/English).
Personal use first; it will become a SaaS later, so keep the code clean, modular and secure from day one.

## Domains for THIS project (all DNS → 104.237.6.214)
| Domain | What we build there | aaPanel site |
|---|---|---|
| **https://aiwazz.in** | **Landing page** of the platform (marketing + SEO pages) | exists (PHP 8.3, SSL active) |
| **https://login.aiwazz.in** | **Login / sign in / sign up**, then the **user dashboard** (TTS tool) and the **API** at `/api/` | exists (PHP 8.3, SSL active) |

- Both aaPanel sites already exist with SSL and are **ready to use for this project**; they are not live products.
- Before replacing anything in their folders, back up the current contents to
  `/root/project-backups/aiwazz-pre-voice-<date>/` and show me what was there.
- **No other domains.** Do not create voice.aiwazz.in or any other site.

## How to start
```
tmux attach -t aiwazz
cd /www/aiwazz
claude --continue
```

## Server facts
- Server: **aiwazz-server** (was cloudwablaster) (104.237.6.214), Ubuntu 24.04, **OpenVZ container**: no GPU, no Docker, no swap.
- tmux session: `aiwazz`.
- pure-ftpd is stopped, disabled at boot and removed from aaPanel's service keep-alive list. Keep it off (use SFTP).
- Checked: 6 GB RAM (~4.5 GB free), 4 threads (Xeon E5-2697 v2), 16 GB disk free, Python 3.12.3.
- Missing: python3-venv, espeak-ng, ffmpeg, dnsutils (install in phase 1, ask first).
- **Install CPU-only PyTorch** (the default CUDA build is several GB).
- aaPanel stack: nginx 1.24, PHP 8.3, MariaDB 10.11, PM2 (+pm2-logrotate), Redis 127.0.0.1:6379, Node 22/24.
- Old backups in /root/site-archive*, /root/project-backups, /www/backup. **Never modify or delete them.**
- `/www/wwwroot/wabacrm-v2` and `default`: leave alone.

## Working rules
- Ask me before deleting anything, touching any database, changing firewall/SSH/panel settings, or editing nginx configs.
- Secrets go in `.env` (chmod 600), never in code or git. Commit a `.env.example`.
- Every app port binds to **127.0.0.1 only**. Public traffic only through nginx + HTTPS.
- No `CORS *` with credentials, no string-built SQL (use the ORM / parameters), no hardcoded secrets,
  no plain-text passwords anywhere (the old project had all of these).
- Small steps: after each phase, show me what changed and how to test it, then check both domains return 200.
- **Git: https://github.com/Radhamadhavmeapi/aiwazz** (monorepo, branch `main`). All code lives in this repo.
  Work flow: edit in the clone at `/www/aiwazz` → commit → push → deploy from the clone. Never edit code
  directly in `/www/wwwroot/*` (those folders only receive built/deployed files).
  Commit after each working phase with clear messages. Never commit `.env`, `storage/`, `.venv/`, `node_modules/`,
  model files or audio. Keep a proper `.gitignore`.
- GitHub access from the server: use an **SSH deploy key with write access** for this repo only
  (`/root/.ssh/aiwazz_deploy`, host alias in `/root/.ssh/config`). Never put a GitHub token in code or in the remote URL.

## Architecture (v1)
```
https://aiwazz.in        → static landing page  (/www/wwwroot/aiwazz.in)
https://login.aiwazz.in  → nginx
     ├── /          → dashboard web app, static build (login, signup, TTS tool, history, account)
     └── /api/      → proxy to 127.0.0.1:8100 (proxy_read_timeout 300s)
                        FastAPI + uvicorn (Python 3.12 venv), PM2 process "voice-api"
                        ├── MariaDB database `aiwazz_voice` (own DB user, localhost only)
                        ├── TTS engine: Kokoro-82M on CPU (default)
                        ├── TTS engine: edge-tts (optional, admin/personal use only)
                        └── storage/audio/ (generated files, auto-delete after 7 days)
```

### Repo layout (cloned at /www/aiwazz)
```
aiwazz/
  landing/     Astro static landing page → build deployed to /www/wwwroot/aiwazz.in
  dashboard/   web app (Vite + React + TS + Tailwind + shadcn/ui) → build deployed to /www/wwwroot/login.aiwazz.in
  api/         FastAPI app (main.py, auth/, tts/, models/, settings.py), Alembic migrations
  tools/       tts.sh for the video pipeline
  ecosystem.config.js   PM2 config
```
The API runs from `/www/aiwazz/api` with its venv, `.env` and `storage/` there, outside the public web root,
so nginx never serves them directly. `tools/deploy.sh` builds and copies `landing/` and `dashboard/` into the web roots
and restarts `voice-api` with PM2.

## Auth (login.aiwazz.in)
- Email + password signup/login. Passwords hashed with **argon2** (or bcrypt).
- Sessions in **httpOnly, Secure, SameSite=Lax cookies**. CSRF protection on POST routes.
- **Signup is invite-only for now** (invite code in .env, or admin approval) so strangers can't use the CPU.
- Roles: `admin` (me) and `user`. Rate-limit login attempts (Redis).
- Forgot-password flow: later. Never email passwords.
- Separate API keys (hashed in DB) for scripts like the video pipeline; header `X-API-Key`.

## TTS engines
- **Kokoro** (`kokoro`, `soundfile`; system `espeak-ng`, `ffmpeg`):
  - Hindi `KPipeline(lang_code='h')`: voices `hf_alpha`, `hf_beta` (female), `hm_omega`, `hm_psi` (male).
  - English `lang_code='a'` (US) / `'b'` (UK).
  - Load pipelines once at startup, **sharing one `KModel`** (`KPipeline(..., model=m)`: 1.3 GB vs 2.7 GB). **One synthesis at a time** (6 GB RAM, no swap) with a simple queue.
  - Apache-2.0, so it's OK for the future SaaS.
  - Measured (phase 1, 4 threads): ~1.35x realtime (60 s of audio ≈ 45 s compute), peak RSS ~1.6 GB during synthesis with shared model.
- **Hinglish:** Kokoro's Hindi voices read Devanagari; Roman Hinglish ("Raat 11 baje customer ne...") sounds wrong.
  Add a "Transliterate Hinglish" toggle: Roman Hindi → Devanagari before synthesis, English words kept as-is.
- **edge-tts** (optional): `hi-IN-MadhurNeural`, `hi-IN-SwaraNeural`. Unofficial Microsoft service:
  admin-only, never offered to SaaS users.

## API (v1)
- `POST /api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `GET /api/auth/me`
- `GET  /api/health`, `GET /api/voices`
- `POST /api/tts` `{text, engine, voice, lang, speed 0.7–1.3, format mp3|wav, transliterate}` → `{id, url, duration_sec}`
  (split into sentences, join with short pauses, max 5,000 chars)
- `GET  /api/history` (last 50 for the user), `GET /api/audio/{id}` (only the owner can download)

## Design system (applies to landing + dashboard)
Goal: a **modern, advanced, technology-focused SaaS** look. Clean, minimal, premium (think Linear, Vercel,
ElevenLabs). Not a template look, no clutter, no stock photos, no random colors.

- **Stack:** dashboard = Vite + React + TypeScript + Tailwind CSS + shadcn/ui + lucide-react icons +
  framer-motion (subtle only). Landing = Astro (static HTML output, best for SEO) + Tailwind, same tokens.
  Shared design tokens (colors, radius, fonts) in one place, used by both.
- **Theme:** dark-first with a light-mode toggle (remember the choice). Neutral base (zinc/slate),
  near-black background `#0A0A0B`, surfaces one step lighter, 1px subtle borders, soft shadows.
  **One accent:** electric violet → cyan gradient, used sparingly (primary button, active states, waveform, key highlights).
- **Typography:** Inter or Geist for UI, Geist Mono / JetBrains Mono for numbers, API keys and code.
  Clear hierarchy, generous spacing, tight letter-spacing on large headings.
- **Signature element:** a live **audio waveform** (wavesurfer.js) in the player and as the landing hero visual,
  animated while generating. Glassy cards with a faint grid/noise background in the hero only.
- **Dashboard layout:** collapsible left sidebar (Generate, History, Voices, API keys, Settings), top bar with
  usage/credits placeholder + theme toggle + avatar menu, ⌘K command palette. Main "Generate" screen:
  large text editor with character counter, right panel with voice picker (voice cards with play-preview),
  language, speed slider, Hinglish toggle, big Generate button; result shows waveform player + download (MP3/WAV) + copy link.
- **States everywhere:** loading skeletons, progress while synthesizing (queue position), empty states with a hint,
  friendly error toasts (sonner). No blank screens.
- **Auth pages (login.aiwazz.in):** split layout. Left: form (email, password, show/hide, invite code on signup).
  Right: brand panel with animated waveform + one-line tagline. Inline validation, password strength meter.
- **Quality bar:** fully responsive (I use my phone a lot), keyboard accessible, visible focus rings,
  WCAG AA contrast, `prefers-reduced-motion` respected. Lighthouse ≥ 90 on the landing page.
  Smooth but fast: animations 150–250 ms, no heavy libraries on the landing page.
- Before building screens, show me the design tokens + one screen (Generate page) for approval first.

## Landing page (aiwazz.in)
Fast static page following the design system above, mobile-first. Hero ("AI voiceovers in Hindi, Hinglish & English"),
audio samples, features, how it works, FAQ, "Sign in / Get invite" buttons → login.aiwazz.in.
SEO: proper title/meta/OG tags, sitemap.xml, robots.txt, pages `/text-to-speech`, `/hindi-text-to-speech`,
`/ai-voiceover-for-reels`. No pricing yet.

## Build phases
-1. **Repo setup:** create the deploy key, show me the public key so I add it in GitHub
   (repo → Settings → Deploy keys → "Allow write access"), clone to `/www/aiwazz`, add this CLAUDE.md,
   `.gitignore`, `README.md`, first commit + push.
0. **Security** (ask before each change; check both domains after each): bind MariaDB to 127.0.0.1,
   disable plain FTP, protect aaPanel ports 21833/888, change the security entrance path, enable 2FA,
   optionally SSH key-only login.
1. Install python3-venv, espeak-ng, ffmpeg, dnsutils. Venv + CPU torch + kokoro. Hindi + English test WAVs.
   Report speed (seconds of audio per second of compute) and RAM use.
2. FastAPI skeleton: health, voices, tts (no auth yet, localhost only). PM2 `voice-api` on 127.0.0.1:8100.
3. Database `aiwazz_voice` + auth (signup invite-only, login, sessions, roles) + API keys.
4. login.aiwazz.in: back up the folder, nginx proxy `/api/` → 8100, deploy the dashboard (login, signup, TTS tool, history).
5. aiwazz.in: back up the folder, deploy the landing page + SEO pages.
6. Hinglish transliteration toggle, edge-tts (admin only), `tools/tts.sh` for the Remotion video pipeline.

## Later (SaaS, don't build yet)
Credits + Razorpay, public signup with email verification, rented GPU for bigger models (Indic Parler-TTS,
voice cloning with consent), contracted voice artists for exclusive "studio voices", maybe its own .com brand.

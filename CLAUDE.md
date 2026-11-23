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
- **CPU has AVX but no AVX2** (Ivy Bridge): some new native binaries crash with "Illegal instruction".
  Example: Astro 7's Rust compiler binding, so `landing/` is pinned to **Astro 6.4.8** (WASM compiler) + **Vite 7**.
  Test new native deps (`node -e "require('x.node')"`) before relying on them.
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
API settings: env vars / `api/.env` with prefix **`AIWAZZ_`** (PM2 injects keys like `env`, `name` into the app's
environment; unprefixed names would collide). PM2 starts the API via `env -i` with an explicit env (no inherited shell vars).
The API runs from `/www/aiwazz/api` with its venv, `.env` and `storage/` there, outside the public web root,
so nginx never serves them directly. `tools/deploy.sh` builds and copies `landing/` and `dashboard/` into the web roots
and restarts `voice-api` with PM2.

## Auth (login.aiwazz.in)
**Built (step 3).** DB `aiwazz_voice` (MariaDB, own user `aiwazz_voice`@localhost/127.0.0.1, ALL on that DB only;
password only in `api/.env`). Migrations: Alembic (`api/migrations`). Redis **db 5**, prefix `aiwazz:` (db 0 = other project).
- Tables: users, sessions (token SHA-256 only), invites (code SHA-256 only, single-use by default, expiry, role),
  api_keys (SHA-256 only, `aiw_live_…`, shown once), generations (owner, settings, 160-char excerpt, results).
- Cookies `__Host-aiwazz_session` (httpOnly) + `__Host-aiwazz_csrf` (JS-readable): Secure, SameSite=Lax, Path=/.
  Writes need `X-CSRF-Token` = CSRF cookie **and** an allowed Origin (`https://login.aiwazz.in`); API-key calls are exempt.
- Rate limits: login 5/15 min per email + 20/15 min per IP, signup 10/h per IP (Redis). Same 404 for "not yours".
- TTS, jobs, audio, history need a session or `X-API-Key`; audio is owner-only (admin: all); expired audio → 410.
- Admin CLI (no default accounts anywhere): `cd api && .venv/bin/python manage.py create-user --email E --role admin`,
  `create-invite [--uses N --days D --label L]`, `list-invites`, `revoke-invite --id N`, `list-users`,
  `set-password --email E`, `set-active --email E --active no`.
- nginx: `deploy/nginx/login.aiwazz.in.conf` → `/www/server/panel/vhost/nginx/extension/login.aiwazz.in/aiwazz.conf`
  (proxy /api/, SPA fallback, HTTP→HTTPS except /.well-known/); `deploy/nginx/aiwazz.in.conf` (HTTP→HTTPS).
  Main aaPanel vhost files are not edited. Always `nginx -t` before `nginx -s reload`.
- Deploy: `tools/deploy-api.sh` (alembic upgrade + PM2 restart + health), `tools/deploy-dashboard.sh` (app at the
  site root, keeps `preview/` + aaPanel files), `tools/deploy-preview.sh`, `tools/deploy-landing.sh`.

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
  - Measured (phase 1, 4 threads): ~1.35x realtime (60 s of audio ≈ 45 s compute), peak RSS ~1.6 GB during synthesis with shared model. End-to-end in the API (phase 2): ≈1.0x of *final* audio (Kokoro pads ~20% silence that gets trimmed; post-processing ≈1 s per job), so a 60 s voiceover ≈ 60 s.
- **Hinglish:** Kokoro's Hindi voices read Devanagari; Roman Hinglish ("Raat 11 baje customer ne...") sounds wrong.
  Add a "Transliterate Hinglish" toggle: Roman Hindi → Devanagari before synthesis, English words kept as-is.
- **edge-tts** (optional): `hi-IN-MadhurNeural`, `hi-IN-SwaraNeural`. Unofficial Microsoft service:
  admin-only, never offered to SaaS users.

## API (v1)
- `POST /api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `GET /api/auth/me`
- `GET  /api/health`, `GET /api/voices`
- `POST /api/tts` `{text, engine, voice, lang, speed 0.7–1.3, format mp3|wav, transliterate, normalize, loudness_lufs}`
  → 202 `{id, status, position}` (queued job); poll `GET /api/tts/jobs/{id}`. `?wait=true` blocks (≤290 s) and returns
  200 `{id, url, urls{mp3,wav}, duration_sec, loudness{…}, timing{…}}`. Split into sentences, join with short pauses, max 5,000 chars.
- **Post-processing (always):** trim silence per sentence, 250 ms pause between sentences / 600 ms between paragraphs,
  10 ms fades + digital silence so each edge ≈ 100 ms. Loudness (default on): two-pass, pass 1 = EBU R128 measure,
  pass 2 = gentle 2:1 RMS compressor (threshold = clip's own loudness, before the gain) + exact linear gain
  + 4x-oversampled true-peak limiter, re-measured until within 0.2 LU of target
  (default **-14 LUFS / -1 dBTP**; per request `loudness_lufs` -30..-8 or `normalize:false`). Not ffmpeg `loudnorm`:
  its linear mode silently falls back to dynamic (AGC) on peaky TTS audio and misses the target on clips < 3 s.
  Output: WAV 16-bit + MP3 192 kbps, both 48 kHz mono, always both files.
- `GET  /api/history` (last 50 for the user), `GET /api/audio/{id}` (only the owner can download)

## Design system (applies to landing + dashboard)
Goal: a **modern, advanced, technology-focused SaaS** look. Clean, minimal, premium (think Linear, Vercel,
ElevenLabs). Not a template look, no clutter, no random colors. Real product screenshots first; free-licence photos
(Unsplash/Pexels) only in landing mood/use-case sections, credited and optimised (rules in `content/LANDING-V2.md`).
**Never** fake testimonials, ratings, logos or user counts.
**Brand:** AiWazz Brand Kit v1.0 in `brand/AiWazz-Brand-Kit/` (read `AiWazz-Brand-Guidelines.pdf`). Tagline **"Type it, hear it."**
(sentence case, with the comma and full stop). Tokens: `design/tokens.css` + `design/theme.css`; web-sized logos, icon,
favicon set and OG image in `design/assets/` (built from the kit by `tools/brand_assets.py`). Live reference:
https://login.aiwazz.in/preview/tokens/

- **Stack:** dashboard = Vite + React + TypeScript + Tailwind CSS + shadcn/ui + lucide-react icons +
  framer-motion (subtle only). Landing = Astro (static HTML output, best for SEO) + Tailwind, same tokens.
  Shared design tokens (colors, radius, fonts) in one place, used by both.
- **Colours (brand kit):** Midnight Navy `#070D25` · Sky Blue `#51B2F6` · Royal Indigo `#2D36DB` (primary) ·
  Electric Violet `#7420DD` · Ink `#0A0A0B` · Cloud `#F4F6FB` · Slate `#64748B`.
  **Brand gradient** `#51B2F6 → #2D36DB → #7420DD` (135°), used sparingly (main button, active states, waveform, key
  highlights); decorative only. Behind white text use the deeper `#1F6FD1 → #2D36DB → #7420DD` (≥ 5.8:1).
- **Theme:** **light by default** on every page of both sites (first visit is always light, not OS-based); dark is optional
  via the toggle and remembered. Light: Cloud background, white surfaces, Midnight Navy text. Dark: Ink background, cool
  surfaces one step lighter, Cloud text. 1px subtle borders, soft shadows.
- **AA contrast rule:** every text colour ≥ 4.5:1, focus rings/UI fills ≥ 3:1. Where a brand colour fails, use a tint
  of the same hue: on Ink, primary fills `#4F58F0` and brand text `#8A90F7` (Royal Indigo is 2.5:1 on Ink), focus ring
  Sky Blue; secondary text `#94A3B8` (dark) / `#475569` (light), since brand Slate is 4.4:1 on Cloud (icons/decor only).
- **Typography (self-hosted, @fontsource):** **Poppins** headings (Latin subsets only), **Inter** UI/body,
  **Montserrat only for the tagline** (`.tagline`), **Noto Sans Devanagari** for Hindi (always, also inside headings),
  Geist Mono for codes, API keys and timecodes. Clear hierarchy, generous spacing, tight tracking on large headings.
- **Logo:** never retype the wordmark, always the artwork. `for-dark` version on dark theme, full colour on light
  (`<Logo>` switches automatically). Min width: with tagline 160 px, without tagline 120 px (use no-tagline in
  headers/sidebar), icon 16 px. No recolouring, shadows or effects; keep clear space. A-Play **icon** in the collapsed
  sidebar, mobile bars and the auth brand panel. **Favicon set** (`03_Favicon` + HTML snippet) at both site roots;
  **OG image** `og-image-light-1200x630.png`.
- **Signature element:** a live **audio waveform** (wavesurfer.js) in the player and as the landing hero visual,
  animated while generating. Glassy cards with a faint grid/noise background in the hero only.
- **Dashboard layout:** collapsible left sidebar (Generate, History, Voices, API keys, Settings), top bar with
  usage/credits placeholder + theme toggle + avatar menu, ⌘K command palette. Main "Generate" screen:
  large text editor with character counter, right panel with voice picker (voice cards with play-preview),
  language, speed slider, Hinglish toggle, big Generate button; result shows waveform player + download (MP3/WAV) + copy link.
- **States everywhere:** loading skeletons, progress while synthesizing (queue position), empty states with a hint,
  friendly error toasts (sonner). No blank screens.
- **Auth pages (login.aiwazz.in):** split layout. Left: form (email, password, show/hide, invite code on signup).
  Right: brand panel with icon, animated waveform + tagline "Type it, hear it." (Montserrat). Inline validation,
  password strength meter.
- **Quality bar:** fully responsive (I use my phone a lot), keyboard accessible, visible focus rings,
  WCAG AA contrast, `prefers-reduced-motion` respected. Lighthouse ≥ 90 on the landing page.
  Smooth but fast: animations 150–250 ms, no heavy libraries on the landing page.
- Before building screens, show me the design tokens + one screen (Generate page) for approval first.

## Landing page (aiwazz.in)
Built (step 2): `landing/` (Astro 6.4.8 + Tailwind v4, same tokens, vanilla JS only: waveform custom element +
one shared audio player). Deploy: `tools/deploy-landing.sh` (keeps `.user.ini`, `.htaccess`, `.well-known/`, `502.html`).
URLs are directory-style with a trailing slash (`/text-to-speech/`); nginx 301s the slashless form, no nginx change needed.
Voice samples: `tools/make_samples.py` → `landing/samples/` (committed). Lighthouse (live): 100/100/100/100.
Fast static page following the design system above, mobile-first. Hero ("AI voiceovers in Hindi, Hinglish & English"),
audio samples, features, how it works, FAQ, "Sign in / Get invite" buttons → login.aiwazz.in.
SEO: proper title/meta/OG tags, sitemap.xml, robots.txt, pages `/text-to-speech`, `/hindi-text-to-speech`,
`/ai-voiceover-for-reels`. Pricing, About, Contact and all policy pages: see `legal/IMPLEMENT.md`
(content in `legal/pages/`, company data and plans in `legal/legal.json`, the single source of truth).

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
7. Legal, pricing and compliance pages (Razorpay + Meta + SEO): `legal/IMPLEMENT.md`.
8. Landing page v2 (more content, visuals, use cases, new SEO pages): `content/LANDING-V2.md`.
9. Learn / docs section at aiwazz.in/learn/ (12 guides): `content/IMPLEMENT-LEARN.md`, content in `content/learn/`.

## Company
AiWazz by TheWebStore028, a brand of **RADHAMADHAV WEBSTORE LLP**, GSTIN 27ABJFR6148J1ZO,
EXOTICA, Casa Rio Main Road, Lotus Pond, Palava City Phase 1, Kalyan, Thane, Maharashtra 421204, India.
Grievance Officer: Ankit Panchal. All of this lives in `legal/legal.json`; never hardcode it elsewhere.

## Later (SaaS, don't build yet)
Credits + Razorpay, public signup with email verification, rented GPU for bigger models (Indic Parler-TTS,
voice cloning with consent), contracted voice artists for exclusive "studio voices", maybe its own .com brand.

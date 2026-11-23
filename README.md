# AiWazz Voice

Text-to-speech platform for short-video voiceovers in Hindi, Hinglish and English.
CPU-only, built on Kokoro-82M (Apache-2.0).

| Domain | What runs there |
|---|---|
| https://aiwazz.in | Static landing page (`landing/`) |
| https://login.aiwazz.in | Dashboard (`dashboard/`) + API at `/api/` (`api/`, FastAPI on 127.0.0.1:8100) |

## Layout
```
landing/     static landing page   → deployed to /www/wwwroot/aiwazz.in
dashboard/   web app (login, TTS)  → deployed to /www/wwwroot/login.aiwazz.in
api/         FastAPI app, PM2 process "voice-api"
tools/       deploy.sh, tts.sh
```

## Workflow
Edit in `/www/aiwazz` → commit → push → `tools/deploy.sh`.
Never edit files directly in `/www/wwwroot/*`. Secrets live in `.env` (see `.env.example`), never in git.

See `CLAUDE.md` for the full spec and build phases.

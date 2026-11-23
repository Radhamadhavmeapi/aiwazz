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

## API (voice-api)

Runs under PM2 as `voice-api` on `127.0.0.1:8100` (config: `ecosystem.config.js`, settings: `api/.env`, see `api/.env.example`).

```bash
pm2 restart voice-api && pm2 logs voice-api
cd api && .venv/bin/python -m pytest -q            # tests (fake engine, no model needed)

curl -s localhost:8100/api/health
curl -s localhost:8100/api/voices
curl -s -X POST 'localhost:8100/api/tts?wait=true' -H 'Content-Type: application/json' \
  -d '{"text":"नमस्ते दोस्तों! यह एक परीक्षण है।","voice":"hf_alpha"}'
curl -s -o out.mp3 'localhost:8100/api/audio/<id>?format=mp3'
```

Setup from scratch: `python3 -m venv api/.venv`, install CPU torch (see `api/requirements.txt`), then
`pip install -r api/requirements-dev.txt`.

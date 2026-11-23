---
slug: /learn/api-quickstart/
title: API quickstart
metaTitle: AiWazz Text to Speech API Quickstart | curl, Python, Node.js
metaDescription: Generate Hindi and English voiceovers from your own code with the AiWazz REST API. API keys, endpoints, examples in curl, Python and Node.js.
order: 7
category: Developers
---

# API quickstart

The API is available on the **Creator** and **Pro** plans. Base URL: `https://login.aiwazz.in/api`

## 1. Create an API key
Dashboard → **API keys** → **Create key**. Copy it immediately; it's shown only once. Keep it secret: anyone with the key can use your characters. Send it in the `X-API-Key` header.

## 2. List voices
```bash
curl -H "X-API-Key: $AIWAZZ_KEY" https://login.aiwazz.in/api/voices
```

## 3. Generate speech (simple, waits for the result)
```bash
curl -X POST "https://login.aiwazz.in/api/tts?wait=true" \
  -H "X-API-Key: $AIWAZZ_KEY" -H "Content-Type: application/json" \
  -d '{"text":"नमस्ते दोस्तों! यह AiWazz का API है।","voice":"hf_alpha","speed":1.0,"loudness_lufs":-14}'
```
Response (shortened):
```json
{"id":"a1b2c3","duration_sec":3.4,"urls":{"mp3":"/api/audio/a1b2c3?format=mp3","wav":"/api/audio/a1b2c3?format=wav"}}
```
Download:
```bash
curl -H "X-API-Key: $AIWAZZ_KEY" -o voice.mp3 "https://login.aiwazz.in/api/audio/a1b2c3?format=mp3"
```

## 4. Long scripts: queue and poll
Without `?wait=true`, `POST /api/tts` returns `202` with `{"id","status","position"}`. Poll `GET /api/tts/jobs/{id}` every 2–3 seconds until `status` is `done`, then download.

### Python
```python
import os, time, requests
API = "https://login.aiwazz.in/api"; H = {"X-API-Key": os.environ["AIWAZZ_KEY"]}
job = requests.post(f"{API}/tts", headers=H, json={"text": "Hello from AiWazz!", "voice": "af_heart"}).json()
while (s := requests.get(f"{API}/tts/jobs/{job['id']}", headers=H).json())["status"] not in ("done", "error"):
    time.sleep(2)
open("voice.mp3", "wb").write(requests.get(f"{API}/audio/{job['id']}?format=mp3", headers=H).content)
```

### Node.js (18+)
```js
const API = "https://login.aiwazz.in/api", H = { "X-API-Key": process.env.AIWAZZ_KEY, "Content-Type": "application/json" };
const job = await (await fetch(`${API}/tts?wait=true`, { method: "POST", headers: H,
  body: JSON.stringify({ text: "Hello from AiWazz!", voice: "af_heart" }) })).json();
const mp3 = await fetch(`${API}/audio/${job.id}?format=mp3`, { headers: H });
await import("node:fs").then(fs => fs.promises.writeFile("voice.mp3", Buffer.from(await mp3.arrayBuffer())));
```

## Request fields
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | string | required | up to 5,000 characters |
| `voice` | string | required | from `/api/voices` |
| `speed` | number | 1.0 | 0.7 – 1.3 |
| `normalize` | boolean | true | loudness levelling on/off |
| `loudness_lufs` | number | -14 | -30 to -8 |

## Errors and limits
| Code | Meaning |
|---|---|
| 401 | missing or wrong API key |
| 402 | not enough characters left in your plan |
| 413 / 422 | text too long or invalid field |
| 429 | queue full or too many requests: retry after a few seconds |

Characters are deducted when a job succeeds; failed jobs are not charged. Audio files are deleted after 7 days.

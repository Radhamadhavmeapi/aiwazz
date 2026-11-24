# Illustrations (landing)

Every illustration slot on aiwazz.in is drawn as inline SVG in `src/components/Illustration.astro`
(brand colours, follows light/dark theme, no people). To replace one with a rendered image
(for example an AI-generated 3D image), add a file here and rebuild — no code change needed:

| Slot | Where | Aspect | Size to export |
|---|---|---|---|
| `problem` | Home: "Recording voiceovers is slow" | 4:3 | 960×720 |
| `reels` | Home use case: Instagram reels | 16:9 | 960×540 |
| `youtube` | Home use case: YouTube explainers | 16:9 | 960×540 |
| `ads` | Home use case: ads & product videos | 16:9 | 960×540 |
| `teachers` | Home use case: courses & teachers | 16:9 | 960×540 |
| `business` | Home use case: business announcements | 16:9 | 960×540 |
| `stories` | Home use case: audiobooks & stories | 16:9 | 960×540 |

`<slot>.webp` is required for the override; `<slot>.avif` is optional (served first when present).
For a separate dark-theme version add `<slot>-dark.webp` (+ optional `.avif`); without it the same image is used in both themes.
Keep each file under ~60 KB.  

Current overrides: `reels` + `reels-dark` (phone mockup of a real dashboard screenshot on a light / dark backdrop, own work).
No stock photos of people are used anywhere on the site (removed 24 Nov 2026).

---
slug: /learn/choosing-a-voice/
title: Choose the right voice
metaTitle: How to Choose an AI Voice for Your Video | AiWazz
metaDescription: Pick the right AiWazz voice for reels, ads, courses and storytelling. Hindi, US English and UK English voices compared.
order: 4
category: Better results
---

# Choose the right voice

AiWazz has 14 voices: 4 Hindi, 6 US English and 4 UK English. Hear them all on the [Voices page](https://login.aiwazz.in/voices) or on the [home page](/#voices).

## Match the voice to the script language
- Hindi or Hinglish script → a **Hindi** voice.
- English script → a **US** or **UK English** voice. Choose the accent your audience expects.

## Match the voice to the content
| Content | Try |
|---|---|
| Instagram reels, Shorts | an energetic, bright voice at speed 1.05–1.15 |
| Ads and offers | a friendly, clear voice; short sentences |
| Explainers and tutorials | a warm, neutral voice at speed 1.0 |
| Stories and narration | a deep, calm voice at speed 0.9–1.0 |
| Courses and training | a steady narrator voice; paragraphs between topics |

## Add a speaking style
A **style** sets pace, pauses and loudness in one tap, with any voice. Pick one under **Style** in the voice panel
(or send `"style"` in the [API](/learn/api-quickstart/)):

| Style | Pace | Pauses | Loudness | Good with |
|---|---|---|---|---|
| **Energetic reel** | 1.12× | short | -14 LUFS | Beta |
| **Calm narrator** | 0.92× | long | -16 LUFS | Psi |
| **Ad announcer** | 1.05× | tight | -14 LUFS | Omega |
| **Friendly explainer** | 1.0× | even | -14 LUFS | Alpha |

A style doesn't change the voice itself. After picking one you can still move the speed slider or change the
loudness; your change wins. Tap the style again to turn it off.

## Tips
- **Preview with your own sentence.** Generate the same 1–2 lines with 2 or 3 voices and compare.
- **Stay consistent.** Use one voice per channel or series so your audience recognises it.
- **Male and female voices for dialogue:** generate each speaker's lines separately with different voices, then combine them in your editor.
- Voice IDs (for the API) look like `hf_alpha` or `am_michael`. Get the full list from `GET /api/voices`.

Next: [Speed, loudness and file formats](/learn/speed-and-loudness/)

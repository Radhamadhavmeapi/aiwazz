---
slug: /learn/using-audio-in-editors/
title: Use your audio in video editors
metaTitle: Add AI Voiceover to CapCut, Instagram, YouTube, Premiere, DaVinci, Canva | AiWazz
metaDescription: Step-by-step: add your AiWazz voiceover to CapCut, Instagram Reels, YouTube Studio, Premiere Pro, DaVinci Resolve, Canva and Remotion.
order: 6
category: Better results
---

# Use your audio in video editors

Download your voiceover as **MP3** (phone editors) or **WAV** (desktop editors) first.

## CapCut (phone or desktop)
1. Open your project → **Audio** → **Extracted / Your sounds** → **Import** (desktop: drag the file onto the timeline).
2. Line the voice up with your clips. Use **Auto captions** to add subtitles from the voiceover.
3. Lower background music: tap the music track → **Volume** around 15–25.

## Instagram Reels editor
1. Make the reel in CapCut or another editor with the voiceover included, then upload. (Instagram's own editor can't import audio files directly.)
2. Keep Instagram's added music low so your voice stays clear.

## YouTube (Shorts and long videos)
- Add the voiceover in your editor before uploading. YouTube Studio's editor can only add music from its library.
- Our default -14 LUFS matches YouTube's loudness target, so YouTube won't turn your video down.

## Adobe Premiere Pro
1. **File → Import** the WAV. Drag it to an audio track.
2. Right-click → **Audio Clip Mixer** if you need to adjust levels; use **Essential Sound → Dialogue** for EQ if you like.
3. Sequence settings at 48 kHz match our files exactly.

## DaVinci Resolve
1. Drag the WAV into the **Media Pool**, then onto the timeline.
2. On the **Fairlight** page, use the music track's ducking (sidechain) to keep music under the voice.

## Canva
1. **Uploads → Upload files** → choose the MP3.
2. Drag it onto your design's timeline and trim as needed.

## Remotion (code-based video)
```tsx
import { Audio, staticFile } from "remotion";
export const Voice = () => <Audio src={staticFile("voiceover.wav")} />;
```
For automation, generate audio with the [API](/learn/api-quickstart/) and save it into `public/`.

## Captions tip
Most editors can auto-generate captions from the voiceover. Check Hindi captions carefully; you can paste your original script to correct them.

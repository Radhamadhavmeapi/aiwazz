# Landing page v2: marketing brief (aiwazz.in)

Goal: turn aiwazz.in from a short page into a **complete, trustworthy, conversion-focused SaaS landing page** that explains everything a first-time visitor needs, ranks on Google, and passes Razorpay/Meta review. Light theme by default. Follow the Design system in CLAUDE.md and the brand kit.

## Hard rules (trust and compliance)

- **No fake social proof.** No invented testimonials, reviews, star ratings, customer logos, user counts or "trusted by 10,000 creators". Leave those sections out until we have real ones. (Fake reviews break consumer-protection rules and Razorpay/Meta policies.)
- **No unverifiable numbers.** Every number on the page must be true for our product today: 14 voices, 3 accents (Hindi, US English, UK English), MP3 + WAV at 48 kHz, -14 LUFS default, 5,000-character script limit per generation, audio kept 7 days, prices from `legal/legal.json`.
- **Real product visuals first.** Use real screenshots of the dashboard (light theme, with realistic Hindi/English sample scripts, no personal data) rendered in clean device frames (laptop + phone).
- **Photos:** allowed for mood/use-case sections only. Use free-licence photos from Unsplash or Pexels (both allow commercial use). Prefer Indian creators, small businesses, teachers, studios, phones filming reels. Rules:
  - Never pair a real person's photo with a quote, name or claim (it would read as a testimonial).
  - Download, crop to the needed aspect ratio, convert to **WebP and AVIF**, max 1600 px wide, ≤ 120 KB each, `loading="lazy"` (except hero), explicit width/height, meaningful `alt` text.
  - Record every photo in `landing/public/photos/CREDITS.md` (photographer, source URL, licence) and credit them on /about/ ("Photos: Unsplash/Pexels contributors").
  - Max 6 photos on the home page; keep Lighthouse performance ≥ 95.
- **Illustrations:** for "how it works" and feature icons use lucide icons and simple brand-gradient shapes, not clip art.

## Home page, section by section

1. **Header (sticky):** logo (no tagline), nav: Features · Voices · How it works · Pricing · Learn · FAQ, buttons "Sign in" (ghost) and "Get started free" (gradient). Mobile: hamburger sheet.
2. **Hero**
   - Eyebrow: "AI text to speech for India"
   - H1: "Turn any script into a natural voiceover in seconds"
   - Sub: "Hindi, Hinglish and English voices for reels, YouTube, ads and courses. Paste your script, pick a voice, download studio-ready audio."
   - Buttons: "Get started free" → signup · "Hear the voices" → #voices
   - Under buttons: "Free plan · No card needed · GST invoice on paid plans"
   - Visual: dashboard screenshot in a laptop frame with the live animated waveform overlay and a small "Playing: Hindi, Alpha" chip. Hero demo player with 2 tabs (Hindi / English) stays.
3. **Proof strip (facts, not claims):** 14 voices · Hindi + English · MP3 & WAV 48 kHz · Ready for reels (-14 LUFS) · Pay in ₹ with UPI.
4. **Problem → solution (with 1 photo):** "Recording voiceovers is slow" (mic setup, retakes, background noise, studio cost) vs "AiWazz: type it, hear it" (minutes, consistent voice, no mic). Photo: creator recording on a phone at a desk.
5. **Voices gallery (#voices):** all 14 voices as cards with play button, name, gender, accent, tone ("warm", "deep narrator"…), filter chips (Hindi / US / UK, Female / Male). Real samples from `landing/samples/`.
6. **How it works (3 steps):** 1 Write or paste your script · 2 Pick a voice and speed · 3 Download MP3/WAV and drop it into your video editor. Short looping screen recording (MP4/WebM, muted, ≤ 1.5 MB, poster image) of the real dashboard doing this.
7. **Features grid (8 cards):** Natural Hindi voices · Hinglish-friendly · English US & UK · Studio-ready loudness (-14 LUFS, true-peak safe) · Clean edges (silence trimmed) · MP3 + WAV 48 kHz · API for automation (Creator plan and above) · Private by default (audio auto-deleted after 7 days, scripts never used for training).
8. **Use cases (6 cards, photos allowed here):** Instagram reels & YouTube Shorts · YouTube explainers · Ads & product videos · Online courses & teachers · Business announcements & IVR-style messages · Audiobooks & stories (only for text you own). Each card: 1-line benefit + "Learn how" link to the matching /learn/ guide.
9. **Before / after audio:** same script: "Phone mic recording" vs "AiWazz voice", only if we record a real phone sample ourselves; otherwise skip this section.
10. **Hindi & Hinglish section:** explain Devanagari input, mixing English words, and that automatic Roman → Devanagari is coming ("rolling out soon" with no date). Show an example script in both scripts.
11. **Works with your tools:** CapCut, Instagram editor, YouTube Studio, Premiere Pro, DaVinci Resolve, Canva, Remotion. Text names in a clean row (no third-party logos unless their brand guidelines allow it), each linking to the matching Learn guide.
12. **Pricing teaser:** the 4 plan cards (compact) from legal.json + "See full pricing" → /pricing/.
13. **Comparison table:** "AiWazz vs recording yourself vs hiring a voice artist": time, cost per minute, retakes, consistency, Hindi support. Honest; no competitor brand names.
14. **Security & privacy:** HTTPS, hashed passwords, audio auto-deleted after 7 days, data stored in India-first infrastructure, GST invoices, Razorpay secure checkout, links to Privacy and Terms.
15. **FAQ (12+ questions):** what is a character, which languages, commercial use per plan, Hinglish, how long generation takes, file formats, loudness, refunds, GST invoice, API, data privacy, can I clone my voice (not yet; future, consent-based only).
16. **Final CTA band (gradient):** "Your next reel needs a voice. Make it in seconds." Buttons: Get started free · Read the Learn guides.
17. **Footer:** as in legal/IMPLEMENT.md section 3, plus a "Learn" column.

## New SEO landing pages (each 800–1,200 words, unique copy, FAQ + samples + CTA)

- /hindi-voice-generator/ · /hinglish-text-to-speech/ · /ai-voice-for-youtube/ · /ai-voice-for-instagram-reels/ · /text-to-speech-for-ads/ · /text-to-speech-for-teachers/ · /english-indian-accent-voiceover/ (only if we add an Indian-English voice; otherwise skip)
- Keep the existing three. Each page: H1 with the keyword, Devanagari variant where relevant, internal links to 2 Learn guides + pricing, `FAQPage` JSON-LD, added to sitemap.

## SEO and performance checklist

- One H1 per page, logical H2/H3, descriptive link text, `alt` on every image, OG + Twitter cards (light OG image), canonical, `hreflang="en-IN"`, sitemap and robots updated, `Organization` + `WebSite` (with SearchAction to /learn/?q=) + `SoftwareApplication` JSON-LD.
- Core Web Vitals: LCP < 2.0 s on 4G, CLS < 0.05, hero image preloaded, fonts `font-display: swap` with Latin subsets.
- Lighthouse 95+ in all four categories on mobile, both themes.

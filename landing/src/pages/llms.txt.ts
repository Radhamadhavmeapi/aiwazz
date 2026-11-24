import type { APIRoute } from "astro";
import { SEO_PAGES } from "../data/site";

export const GET: APIRoute = () =>
  new Response(
    `# AiWazz

> AI text to speech for India: natural Hindi, Hinglish and English voiceovers for reels, YouTube, ads and courses.
> 14 voices (4 Hindi, 6 US English, 4 UK English), MP3 and WAV at 48 kHz, levelled to -14 LUFS. Prices in INR.

## Product
- [Home](https://aiwazz.in/)
- [Pricing](https://aiwazz.in/pricing/)
${SEO_PAGES.map((p) => `- [${p.label}](https://aiwazz.in${p.href})`).join("\n")}

## Docs
- [Learn hub](https://aiwazz.in/learn/)
- [Getting started](https://aiwazz.in/learn/getting-started/)
- [Hindi and Hinglish guide](https://aiwazz.in/learn/hindi-and-hinglish/)
- [Fix pronunciation](https://aiwazz.in/learn/fix-pronunciation/)
- [API quickstart](https://aiwazz.in/learn/api-quickstart/)

## Company
- [About](https://aiwazz.in/about/)
- [Contact](https://aiwazz.in/contact/)
- [Terms](https://aiwazz.in/terms/)
- [Privacy](https://aiwazz.in/privacy/)
`,
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );

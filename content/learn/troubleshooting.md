---
slug: /learn/troubleshooting/
title: Troubleshooting
metaTitle: AiWazz Troubleshooting | Fix Common Voiceover Problems
metaDescription: Fixes for common AiWazz issues: wrong pronunciation (pronunciation list), Hindi sounding English, slow generation, download problems, login and payment issues.
order: 10
category: Help
---

# Troubleshooting

## The Hindi voice sounds like it's reading English
Your Hindi is probably in Roman letters ("aaj hum…"). Turn on **Transliterate Hinglish** in the voice panel, or write it in Devanagari. See the [Hindi and Hinglish guide](/learn/hindi-and-hinglish/).

## A word is mispronounced
Fix it once and it stays fixed: add it to **Settings → Pronunciations** (word → how to say it, with a free ▶ test), or
for one script write `[word](say it as)`, for example `[Kalyan](कल्याण)`. Check the **Will be read as** box under the
editor before you generate. See [Fix pronunciation](/learn/fix-pronunciation/).

## My pronunciation fix isn't used
- The word must match as a **whole word**: `GST` doesn't change "GSTIN". Add the longer word as its own entry.
- In the script, the brackets must touch: `[word](say it as)`, with no space between `]` and `(`.
- A fix in the script wins over your list, and your list wins over the built-in list.
- With Transliterate Hinglish on, a fix is read exactly as typed. Write Hindi sounds in Devanagari.

## Generation is taking a long time
Generations run in a queue. A 60-second voiceover usually takes about a minute once it starts. If you see a queue position, other jobs are ahead of you. Long scripts: split them into scenes. If a job seems stuck for more than 10 minutes, refresh the page; failed jobs never use your characters.

## "Not enough characters"
You've used this period's characters (see the top bar or **Settings → Billing**). Characters reset on the 1st of every month. **Coming soon:** online upgrades; during early access, [contact us](/contact/) to change your plan.

## The audio is too quiet or too loud in my video
Keep loudness levelling on (default -14 LUFS). In your editor, check you haven't lowered the voice track, and keep background music 15–20 dB below the voice.

## I can't find an old file
Audio is kept for 7 days. After that, History still shows the item and the first 160 characters of the script; paste your full script again to regenerate it.

## Download doesn't start on my phone
Long-press the download button and choose **Download link**, or open the dashboard in Chrome or Safari instead of an in-app browser (Instagram/WhatsApp).

## I can't sign in
Check your email address for typos. **Coming soon:** a Forgot password link; until then, [contact us](/contact/) from your registered email. After several wrong attempts, sign-in is paused for a few minutes for your safety.

## Payment went through but my plan didn't change
**Coming soon:** online payments. Once they open: wait 2–3 minutes and refresh; if it's still not updated after 24 hours, email support with your Razorpay payment ID (starts with `pay_`). See our [Shipping and Delivery Policy](/shipping-policy/).

## Still need help?
[Contact us](/contact/) with your registered email, what you tried and a screenshot.

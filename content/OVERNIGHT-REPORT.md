# Overnight report: 23 → 24 November 2026

All seven items ran in order. Before each phase I pulled and re-read CLAUDE.md. After each one I ran the tests, committed,
pushed, deployed and checked that both domains return **200**. They did every time. Test accounts were created through
invites and deleted afterwards. The database now holds only your admin account.

## 1. What's done

| # | Phase | Commit | Highlights |
|---|---|---|---|
| 1 | Step 4: dashboard wired to the API | `dd07fb1` | Real generation with live queue/progress, History, Voices, API keys, Settings (password, sign out other devices, **delete account**) |
| 2 | Phase 6: Hinglish + `tools/tts.sh` | `7d8d109` | Roman Hindi → Devanagari with English words kept, live "Will be read as" preview, CLI for the video pipeline. edge-tts skipped, as you asked. |
| 3 | Phase 7: legal, pricing, compliance | `14e22fb` | 10 policy pages + pricing from `legal.json`, company footer on both sites, signup consent stored, contact form, 301 aliases, JSON-LD |
| 4 | Phase 8: landing v2 + 6 SEO pages | `91303d7` | Rebuilt home with real dashboard screenshots and screen recording, 6 credited Pexels photos, voices gallery, comparison table, 13 FAQs |
| 5 | Phase 9: Learn | `7c07b11` | `/learn/` hub with search + 11 guides checked against the product; built plans and character quota (402), usage display, delete from History |
| 6 | Phase 10: Voice Lab | `44b2c11` | 16 samples, research on open models and paid APIs, recommendation. **Also fixed a live bug:** "₹" was dropped and "2,00,000" was read digit by digit. |
| 7 | Final check | `6893544` | Lighthouse ≥ 97 everywhere (table below); login/signup now indexable; llms.txt |

### New and changed pages

**aiwazz.in**
- Home (v2): https://aiwazz.in/
- Pricing: https://aiwazz.in/pricing/
- About: https://aiwazz.in/about/
- Contact (with form): https://aiwazz.in/contact/
- Terms: https://aiwazz.in/terms/
- Privacy: https://aiwazz.in/privacy/
- Refund policy: https://aiwazz.in/refund-policy/
- Shipping & delivery: https://aiwazz.in/shipping-policy/
- Acceptable use: https://aiwazz.in/acceptable-use/
- Data deletion: https://aiwazz.in/data-deletion/
- Grievance: https://aiwazz.in/grievance/

**New SEO pages**
- https://aiwazz.in/hindi-voice-generator/
- https://aiwazz.in/hinglish-text-to-speech/
- https://aiwazz.in/ai-voice-for-youtube/
- https://aiwazz.in/ai-voice-for-instagram-reels/
- https://aiwazz.in/text-to-speech-for-ads/
- https://aiwazz.in/text-to-speech-for-teachers/

**Learn**
- Hub with search: https://aiwazz.in/learn/ (also works with `?q=`)
- Guides: [getting-started](https://aiwazz.in/learn/getting-started/), [writing-scripts](https://aiwazz.in/learn/writing-scripts/),
  [hindi-and-hinglish](https://aiwazz.in/learn/hindi-and-hinglish/), [choosing-a-voice](https://aiwazz.in/learn/choosing-a-voice/),
  [speed-and-loudness](https://aiwazz.in/learn/speed-and-loudness/), [using-audio-in-editors](https://aiwazz.in/learn/using-audio-in-editors/),
  [api-quickstart](https://aiwazz.in/learn/api-quickstart/), [plans-and-billing](https://aiwazz.in/learn/plans-and-billing/),
  [account-and-security](https://aiwazz.in/learn/account-and-security/), [troubleshooting](https://aiwazz.in/learn/troubleshooting/),
  [glossary](https://aiwazz.in/learn/glossary/)

**Site files**
- https://aiwazz.in/sitemap.xml (32 URLs)
- https://aiwazz.in/robots.txt
- https://aiwazz.in/llms.txt

**login.aiwazz.in**
- Sign in: https://login.aiwazz.in/login
- Sign up (consent checkbox, `?plan=` note): https://login.aiwazz.in/signup
- Dashboard: https://login.aiwazz.in/generate, /history, /voices, /api-keys, /settings
- Voice Lab (hidden, noindex): https://login.aiwazz.in/preview/voice-lab/

### New backend pieces

All of these are tested: 55 API tests pass.
- **Auth and account:** `GET /api/auth/session`, `POST /api/auth/password`, `/logout-others`, `/delete-account` (with a reference ID and a last-admin guard).
- **Hinglish and contact:** `POST /api/transliterate`, `POST /api/contact` (stored in the database, also proxied on aiwazz.in).
- **Usage and history:** `GET /api/usage`, `DELETE /api/history/{id}`.
- **Plans:**
  - each user has a `plan` (free | starter | creator | pro) with a monthly allowance from `legal.json`
  - only successful jobs count, and going over returns **402**
  - API keys need Creator or Pro; admins are unlimited
- **New `manage.py` commands:** `set-plan`, `list-messages`, `mark-handled`.
- **Text normalisation:** ₹ and Indian-format numbers are now read correctly in production.

### Learn guides: what didn't match the product, and what I changed

| Guide | Mismatch found | What I changed |
|---|---|---|
| getting-started | Asked for a "name" (no such field); said signups are "reviewed"; button was called "Generate" | Email + password only; invite-only; consent tick box; **Generate voiceover** (phone: Generate) |
| hindi-and-hinglish | Said Roman → Devanagari was "coming soon" | It's live: explains **Transliterate Hinglish** and the "Will be read as" preview |
| speed-and-loudness | Said "Advanced options" | Changed to **Output & loudness**, listing -14/-16/-18/-23 LUFS and the normalization switch |
| api-quickstart | Missing `format`/`transliterate` fields, 403, `/api/usage`; listed 413 | Added them; length errors are 422. **Built:** 402 quota and the Creator/Pro API gate. |
| plans-and-billing | Upgrade, invoices, billing details and cancel don't exist | Marked **Coming soon** ("contact us during early access"). **Built:** characters reset monthly (India time), usage shown in the app. |
| account-and-security | Said "scripts stay until you delete them"; mentioned change email; wrong password location | History keeps 160 characters, and **Delete from History** is now built. Change email is **Coming soon**. Password is under **Settings → Password**. |
| troubleshooting | Forgot password, online upgrade and payments don't exist; said "generate again from History" | Marked **Coming soon** with a contact-us fallback; regenerating means pasting the script again |
| choosing-a-voice, writing-scripts, using-audio-in-editors, glossary, index | No mismatches | Unchanged. The home page tool links now point to the editors guide's real headings. |

## 2. Blocked or skipped, and why

1. **No email is sent anywhere.** The contact form stores messages in the database (read them with `manage.py list-messages`). The deletion confirmation reference is shown on screen and logged, but not emailed. There's no "forgot password" yet. All three need a mail provider (decision 1).
2. **No online billing (Razorpay).** Upgrades, invoices, cancellation and payments are labelled "Coming soon" in Learn and Settings. Plans can only be changed with `manage.py set-plan`.
3. **LLPIN is missing** in `legal.json`, so it's hidden everywhere: Terms keeps only "(GSTIN …)".
4. **Skipped by the brief's own rules:**
   - `/english-indian-accent-voiceover/`: we have no Indian-English voice yet.
   - The before/after audio section: we have no real phone recording.
   - "Was this helpful 👍👎": it would need a backend.
5. **Voice Lab Track B:**
   - Every named open model fails a hard limit (RAM, CPU, or a non-commercial licence).
   - The two small Pocket-TTS Hindi models need a consenting voice speaker and a Hugging Face account, so I didn't download them.
6. **Sarvam premium voices:** their terms forbid reselling the API as a hosted service without a written agreement.
7. **Photos:** all six are from Pexels; I found nothing suitable on Unsplash. The "reels" photo shows a non-Indian person, because I couldn't find a licence-verified Indian one.
8. **Unchanged from before:** whether the server's hostname survives a reboot depends on your VPS panel, which I can't change.

## 3. Decisions I need from you

1. **Email provider** for the contact form, deletion confirmations and forgot password (for example Amazon SES, Zoho ZeptoMail or Postmark). Then I can wire all three.
2. **Signup:** the landing page says "Get started free", but signup still needs an invite (there's a small note under the button). Open signup on the Free plan, or keep it invite-only?
3. **"Coming soon" on public pages:** the legal brief says never to show "coming soon"; the Learn brief asks for it on unbuilt features. I followed the Learn brief inside the Learn guides only. Remove those lines before the Razorpay review, or build billing first?
4. **LLPIN:** add it to `legal/legal.json` and the line reappears automatically.
5. **Commercial-use claim:** the site now says "paid plans include commercial rights". Please confirm that wording, since it's your licence promise. (Kokoro and its voices are Apache-2.0.)
6. **Plans:** should early-access friends get Creator, so they can use the API? `manage.py set-plan --email … --plan creator`
7. **Voice Lab:** pick voices on the preview page (below). I'll ship the approved blends and presets in about half a day.
8. **Photos:** keep, replace, or drop any of the six? Credits are in `landing/media/photos/CREDITS.md` and on /about/.

## 4. Voice Lab

**https://login.aiwazz.in/preview/voice-lab/**
- 16 samples, using the same post-processing as production.
- Rate them with 👍/👎 and notes, which stay in your browser.
- Full write-up: `content/VOICE-LAB-REPORT.md`.

**My top picks.** These rest on measurements only: I can't listen, so your ears decide.
- **New voices (blends):**
  - **Dev** (M): hm_psi 60 + am_fenrir 40. The most distinct.
  - **Naina** (F): hf_beta 60 + af_bella 40.
  - **Arjun** (M): hm_psi 70 + bm_george 30.
  - Then Kabir, Asha and Riya.
  - Probably skip Vikram and Meera: their voice vectors are very close to Psi and Alpha.
- **Tone presets:** Energetic reel, Calm narrator, Ad announcer, Friendly explainer.
- **Proposed line-up:** 10 Hindi/Indian voices (the 4 current + 6 blends) and 4 presets.
- **Cost of adding them:** every candidate runs at 0.78–0.86× real time, needs no extra RAM or disk, and is Apache-2.0.
- **Indian English:** the a1-* samples are the Hindi voices reading English. The accent comes from the voice's timbre only, so listen before deciding.

## 5. URLs for Razorpay and Meta

| Where | Field | URL |
|---|---|---|
| Razorpay → Business website details | Website | https://aiwazz.in/ |
| | About us | https://aiwazz.in/about/ |
| | Contact us | https://aiwazz.in/contact/ |
| | Pricing | https://aiwazz.in/pricing/ |
| | Terms and Conditions | https://aiwazz.in/terms/ |
| | Privacy Policy | https://aiwazz.in/privacy/ |
| | Cancellation and Refund Policy | https://aiwazz.in/refund-policy/ |
| | Shipping and Delivery Policy | https://aiwazz.in/shipping-policy/ |
| Meta → App Dashboard → Basic settings | Privacy Policy URL | https://aiwazz.in/privacy/ |
| | Terms of Service URL | https://aiwazz.in/terms/ |
| | User data deletion → Data deletion instructions URL | https://aiwazz.in/data-deletion/ |
| Also useful | Acceptable Use · Grievance | https://aiwazz.in/acceptable-use/ · https://aiwazz.in/grievance/ |

Checks run on every policy URL:
- Each returns 200 over HTTPS, without login, as static HTML, for a browser, `facebookexternalhit/1.1` and `Razorpay` user agents.
- Business name, address, GSTIN, email and phone are identical on Contact, About, Terms, Privacy and the footer.
- No "lorem", "TODO" or empty sections on the policy pages.
- Aliases like `/terms-and-conditions` and `/privacy-policy` 301-redirect to the right page.

## 6. Lighthouse (mobile, live site)

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| https://aiwazz.in/ | 97–99 | 100 | 100 | 100 |
| https://aiwazz.in/pricing/ | 100 | 100 | 100 | 100 |
| https://aiwazz.in/learn/hindi-and-hinglish/ | 100 | 100 | 100 | 100 |
| https://login.aiwazz.in/login | 100 | 100 | 100 | 100 |

Fixes from the final run:
- **Home, layout shift:** Poppins 700 is now preloaded, taking CLS from 0.13 to 0.
- **Home, load time:** the screen recording starts only when scrolled into view.
- **Learn and login:** tap targets made bigger.
- **Login:** a quiet session check (no 401 in the console), and /login and /signup made indexable.

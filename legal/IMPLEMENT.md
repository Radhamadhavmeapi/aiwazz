# AiWazz legal pages: implementation brief for Claude Code

Goal: aiwazz.in and login.aiwazz.in are ready for **Razorpay website verification**, **Meta app / WhatsApp Business API review**, and **SEO**. All content is in `legal/pages/*.md`. All company data is in `legal/legal.json`.

## 0. Default theme: LIGHT (both sites)

- **Light theme is the default** on aiwazz.in and login.aiwazz.in (landing, auth pages, dashboard, legal pages). Dark is optional via the sun/moon toggle and is remembered per visitor (localStorage, wrapped in try/catch).
- Do not follow `prefers-color-scheme` for the default: first visit is always light. Set the theme class before first paint (inline script in `<head>`) to avoid a flash.
- Logo: full-colour version on light, `for-dark` on dark (`<Logo>` already switches). `<meta name="theme-color">` = Cloud `#F4F6FB` on light, Ink on dark.
- Update CLAUDE.md, design/README.md and the /preview/tokens/ page to say light-first.

## 1. Pages (Astro, on aiwazz.in)

Create one page per markdown file, with a shared `LegalLayout` that follows the brand design system (readable 70ch column, table styling, TOC on desktop for long pages, "Last updated" line, print-friendly).

| File | URL |
|---|---|
| about.md | /about/ |
| contact.md | /contact/ |
| pricing.md | /pricing/ |
| terms.md | /terms/ |
| privacy.md | /privacy/ |
| refund-policy.md | /refund-policy/ |
| shipping-policy.md | /shipping-policy/ |
| acceptable-use.md | /acceptable-use/ |
| data-deletion.md | /data-deletion/ |
| grievance.md | /grievance/ |

- Replace `{{tokens}}` with values from `legal/legal.json` (dotted paths, e.g. `{{grievanceOfficer.name}}`, `{{plans.0.characters}}`, `{{websites.app}}`). Fail the build if a token is unknown.
- **Never publish a placeholder.** If a value is empty (currently only `llpin`), remove the whole table row, list item or line containing it, and tell the owner it is still missing.
- HTML comments starting with `Implementation:` are instructions for you, not page content.
- Add 301 redirects for common aliases: /terms-and-conditions → /terms/, /privacy-policy → /privacy/, /refund → /refund-policy/, /cancellation-policy → /refund-policy/, /shipping → /shipping-policy/, /delivery-policy → /shipping-policy/.

## 2. Pricing page

Build plan cards from `legal.json → plans`: Free ₹0 / Starter ₹199 / Creator ₹499 / Pro ₹1,499 per month (monthly/yearly toggle, yearly = 12 × monthly × (1 − yearlyDiscountPercent/100), "+ 18% GST" note, "Most popular" on Creator, show characters/month and ≈ minutes of audio at ~800 characters per minute). Add a small comparison line under the cards: "Up to 70% less than popular global voice tools, billed in rupees with a GST invoice." (no competitor names). Also add a Pricing section teaser on the home page linking to /pricing/. Buttons go to `https://login.aiwazz.in/signup?plan=<id>`. Prices must be visible without login (Razorpay requirement).

## 3. Footer on BOTH sites (landing + dashboard + auth pages)

Columns: **Product** (Pricing, Text to speech, Hindi text to speech, AI voiceover for reels) · **Company** (About, Contact, Grievance) · **Legal** (Terms, Privacy, Refund policy, Shipping & delivery, Acceptable use, Data deletion).
Bottom line, always visible:
`© 2026 RADHAMADHAV WEBSTORE LLP · AiWazz is a brand of TheWebStore028 · GSTIN 27ABJFR6148J1ZO · <address> · <supportEmail> · <phone>`
On login.aiwazz.in link to the aiwazz.in URLs. Add "Pricing" to the landing header nav.

## 4. Signup and account (login.aiwazz.in)

- Required checkbox on signup: "I agree to the Terms and Conditions, Privacy Policy and Acceptable Use Policy" (links open in a new tab). Store `consent_at`, `terms_version` (= lastUpdated) and IP in the users table.
- Optional, unchecked: "Send me product updates" (`marketing_opt_in`).
- Settings → Account → **Delete account** (type DELETE to confirm): deletes the user, scripts, audio, API keys, sessions; keeps only billing records. Log a deletion reference ID and email it.
- Settings → Billing: placeholder for now (plan, cancel plan). Razorpay checkout comes later.

## 5. Content consistency fixes on existing pages

- Commercial-use claim: change to "**Paid plans** include commercial rights (ads, client work, monetised videos). The Free plan is for personal use." and link to /terms/. Update FAQ answers accordingly.
- "-14 LUFS is the level Reels/Shorts/TikTok play at" → "the loudness most short-video platforms target".
- "Real, unedited output" → "Real output, only loudness-levelled".
- Remove the claim that other tools treat Hindi as an extra language.
- SEO pages: Features / How it works links → /#features and /#how-it-works.
- Hindi page: add a Devanagari H2 "हिंदी टेक्स्ट टू स्पीच" and natural Hindi wording in the copy.

## 6. SEO

- Unique `<title>` and meta description from each file's front matter, canonical URL, OG/Twitter tags (light OG image `og-image-light-1200x630.png`), `lang="en-IN"`.
- Add all new URLs to sitemap.xml (legal pages priority 0.3, pricing 0.8, about/contact 0.5). robots.txt allows everything except /api/.
- JSON-LD:
  - Site-wide `Organization`: name AiWazz, legalName RADHAMADHAV WEBSTORE LLP, url, logo, email, telephone, `PostalAddress` (streetAddress "EXOTICA, Casa Rio Main Road, Lotus Pond, Palava City Phase 1", addressLocality Kalyan, addressRegion Maharashtra, postalCode 421204, addressCountry IN), `taxID` GSTIN, `sameAs` [thewebstore028.com, radhamadhavwebstore.com], `contactPoint` (customer support, en/hi, IN).
  - /pricing/: `SoftwareApplication` (applicationCategory MultimediaApplication, operatingSystem Web) with `offers` per plan in INR, plus `FAQPage`.
  - Legal pages: `BreadcrumbList`.
- Internal links: every page reachable from the footer and listed in the sitemap. Lighthouse SEO and Accessibility must stay at 100.

## 7. Razorpay and Meta compliance checks (verify before reporting done)

- Every URL in section 1 returns **200** over HTTPS, without login, without JS-only rendering (static HTML), not geo-blocked.
- Requests with user agents `facebookexternalhit/1.1` and `Razorpay` get 200 (no bot blocking, no WAF challenge).
- Business name, address, email and phone are identical on Contact, About, Terms, Privacy and the footer, and match legal.json.
- Privacy policy includes: data collected, purposes, sharing, retention, security, user rights, and a clear **deletion path** (in-app + email). Data Deletion page exists at /data-deletion/.
- No "lorem", "TODO", "coming soon" or empty sections anywhere on public pages.
- Print a final table of URLs for me to paste into Razorpay (Business website details) and Meta (App Dashboard → Basic settings: Privacy Policy URL, Terms of Service URL, User data deletion → Data deletion instructions URL).

Commit ("Add legal and policy pages"), deploy both sites, push, and report.

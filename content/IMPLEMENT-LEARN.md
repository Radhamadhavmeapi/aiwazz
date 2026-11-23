# Learn section: implementation brief (aiwazz.in/learn/)

Content lives in `content/learn/*.md` (front matter: slug, title, metaTitle, metaDescription, order, category).

## Pages
- `/learn/` hub: hero with a search box (client-side search over titles, headings and text; tiny index built at build time, no external service), category cards (Start here · Better results · Developers · Account and billing · Help), "Popular guides" row.
- One page per file at its `slug`. Layout: left sidebar with all guides grouped by category (collapsible on mobile), main article (max 72ch), right "On this page" TOC from H2s on desktop, "Previous / Next" links by `order`, "Was this helpful? 👍 👎" (stores a count only, no personal data; skip if it needs a backend), "Still stuck? Contact us" box.
- Code blocks: syntax highlighting at build time (Shiki), copy button, Geist Mono. Tables responsive (horizontal scroll). Devanagari renders with Noto Sans Devanagari.
- Light theme default, dark toggle, same header/footer as the landing page; add **Learn** to the header nav and a **Learn** column in the footer (Getting started, Hindi & Hinglish, API quickstart, Troubleshooting).

## SEO
- `<title>`/meta from front matter, canonical, OG (light image), `BreadcrumbList` (Home › Learn › Guide) and `TechArticle` JSON-LD with `dateModified`; FAQ-style pages (troubleshooting) also `FAQPage`.
- Add all Learn URLs to sitemap.xml (priority 0.6). Internal links: every SEO landing page links to 2 relevant guides, and every guide links back to signup and pricing at the end.

## Keep docs true to the product
The guides describe the product as it will be at launch. Before publishing, compare every guide with the real app and API:
- If a described feature exists: make the docs match it exactly (menu names, field names, error codes, limits).
- If a feature is small and within the plan (Voices page, Settings → Account, change password, delete account, API keys page, 402 "not enough characters", characters deducted only on success): build it.
- If a feature is not built yet (forgot password, billing/invoices, change email): mark that paragraph "Coming soon" in the guide, and list it for me.
- In the dashboard, add a "?" help link in the top bar to /learn/ and contextual links (Generate screen → Writing scripts and Hindi guide; API keys page → API quickstart).
- Report a table: guide → mismatches found → what you changed.

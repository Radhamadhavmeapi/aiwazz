# AiWazz Admin Panel: complete SaaS back office (phase 12)

URL: **https://login.aiwazz.in/admin** · same app, separate code-split bundle · same design system (light default, dark toggle) · fully responsive (owner uses a phone a lot).
Built once, properly, as a real SaaS back office, even though it is used privately at first.

## 0. Security foundation (build first, nothing else ships without it)
- **RBAC roles:** `owner` (everything, only one can transfer ownership), `admin` (everything except roles/ownership/secrets), `support` (users read, invites, messages, moderation), `finance` (billing, invoices, GST exports, refunds), `viewer` (read-only dashboards). Permissions are checked **server-side on every endpoint**, never only in the UI. Non-staff get a plain 404 for every /admin and /api/admin route.
- **2FA mandatory** for every staff role: TOTP (QR setup, 10 single-use backup codes shown once, stored hashed). /admin stays locked until 2FA is set up.
- **Step-up re-auth** (password + TOTP, valid 10 min) for sensitive actions: refunds, plan/price changes, role changes, deleting users, exporting data, editing company/legal data, maintenance mode, revealing nothing secret ever (secrets are never shown, only "set/not set").
- **Audit log** (append-only `admin_audit`: actor, role, action, target, before/after JSON diff, IP, user agent, time). Shown on the Audit page with filters; cannot be edited or deleted from the UI.
- Admin session: shorter idle timeout (30 min), "sign out all admin sessions", optional IP allowlist setting (off by default because the owner's IP changes).
- Rate limits on admin APIs; CSRF + Origin checks as in the rest of the app.
- **Privacy rule:** scripts and audio of users are hidden by default. Viewing them requires a reason (dropdown: abuse report, support request with consent, legal request) and is audited. Matches the Privacy Policy.
- **Impersonation ("view as user")**: read-only, banner shown, time-limited (15 min), audited; can never generate, pay, change password or delete.

## 1. Layout
Left sidebar (collapsible, grouped): Overview · Analytics · Users · Subscriptions · Payments · Invoices · Plans & pricing · Coupons · Invites & waitlist · Support inbox · Moderation · Voices & styles · Pronunciations · API & usage · Queue & jobs · System health · Logs · Email · Announcements · Compliance · Settings · Team & roles · Audit log.
Top bar: global search (users by email/ID, payment IDs `pay_…`, invoice numbers, subscription IDs) via ⌘K, environment badge (TEST / LIVE payments), notifications bell, theme toggle, avatar.
Every list: server-side pagination, sorting, filters, saved views, column chooser, CSV export (export = step-up + audit). Empty, loading and error states everywhere.

## 2. Overview (home)
KPI cards with trend vs previous period: MRR, ARR, active paid subscriptions, new signups (today/7d/30d), trial→paid / free→paid conversion, churn (logo + revenue), ARPU, net revenue this month (after refunds), characters generated today/month, generations today, average queue wait, failed jobs (24h), failed payments (7d).
Charts: revenue (daily/monthly), signups, generations, characters by plan, plan mix donut.
Lists: latest signups, latest payments, open support messages, flagged content, system alerts.

## 3. Analytics
Date range picker + compare. Funnels: landing visit (server log based, no third-party trackers) → signup → first generation → paid. Cohort retention table (weekly). Voice/style/language popularity, Hinglish toggle usage, average script length, API vs web usage, top users by characters, revenue by plan and by state (for GST). All from a nightly `metrics_daily` aggregation table (plus live "today" numbers), so dashboards stay fast.

## 4. Users
Table: email, name, plan, status (active/suspended/deleted), signup date, last active, characters this cycle, lifetime revenue, tags.
User detail page tabs: Profile · Plan & usage (current cycle, history chart, bonus characters) · Subscription & payments · Invoices · Generations (metadata only by default; content behind the privacy rule) · API keys (list, last used, revoke) · Sessions (revoke) · Consent records · Notes (internal) · Activity timeline · Audit.
Actions: change plan (with expiry date), add/remove bonus characters (reason required), extend trial, suspend/unsuspend (reason, user sees a friendly message), force password reset email, revoke all sessions, resend verification, export user data (DPDP), delete user (step-up; follows the deletion rules: billing records kept 8 years), impersonate (read-only).
Bulk actions with confirmation: tag, change plan, send email.

## 5. Billing (Razorpay)
- **Subscriptions:** status (created/authenticated/active/pending/halted/cancelled/completed), plan, cycle dates, next charge, cancel at period end / cancel now (step-up), pause/resume, change plan (upgrade now with proration, downgrade at period end).
- **Payments:** all payments incl. failed, method (UPI/card/netbanking/wallet), Razorpay IDs, GST split, link to Razorpay dashboard. **Refunds:** full/partial with reason (step-up), creates a credit note automatically, status synced by webhook.
- **Invoices & credit notes:** list, download PDF, regenerate PDF (never renumber), void with credit note. Series `AWZ/<FY>/<n>`, credit notes `AWZ-CN/<FY>/<n>`.
- **Dunning:** failed-payment list, retry status, automatic emails (day 0, 3, 7), grace period setting, auto-downgrade to Free after grace.
- **Webhooks log:** every Razorpay event received, signature result, processed/failed, replay button (idempotent).
- **GST reports (finance):** monthly export CSV/Excel for the CA: invoice-wise register, B2B (with GSTIN) vs B2C, state-wise place of supply, CGST/SGST/IGST totals, HSN/SAC summary, credit notes. Also TDS-friendly payment summary.

## 6. Plans & pricing
Edit plan name, characters/month, features list, monthly/yearly price, yearly discount, visibility (public/hidden/legacy), sort order, "most popular" badge. Razorpay plans are immutable, so a price change **creates a new Razorpay plan version**; existing subscribers stay on their old price (grandfathered) unless migrated explicitly. Changing public plans updates `legal/legal.json` through a validated write + triggers the landing rebuild/deploy (step-up, audited, shows a preview diff first).

## 7. Coupons & promotions
Discount codes: % or fixed ₹, plan restriction, monthly/yearly, first payment only or N cycles, max redemptions, per-user limit, start/end date, active toggle; redemption list. Implemented with Razorpay offers/discounts or as a first-invoice discount, whichever Razorpay subscriptions support cleanly (document the choice). Referral program: build data model + admin settings, keep the user-facing part behind a feature flag (off).

## 8. Invites & waitlist
Create invites (uses, days, role, label, optional plan + plan_until for early-access friends), copy once, revoke. Waitlist / "Request an invite" submissions: approve (creates invite + emails it), reject (optional email), bulk approve. Signup mode setting: invite-only / open / closed.

## 9. Support inbox
Contact-form messages + invite requests + grievance/abuse reports in one inbox: status (new/open/waiting/resolved), assignee, priority, internal notes, reply by email from the panel (sent from support@aiwazz.in through our own mail server, threaded by Message-ID), canned replies, link to the user's profile. Grievance items show the legal timelines (acknowledge 24 h, resolve 15 days) with overdue highlighting.

## 10. Moderation & trust
- Automatic flags on generations: keyword/pattern rules (impersonation of officials/banks, OTP/KYC scam phrases, threats, explicit content), unusual volume spikes, many accounts from one IP.
- Queue of flagged items (content viewable under the privacy rule), actions: dismiss, warn user, suspend, delete audio, report note.
- Rule editor (patterns, severity, action), blocklist of emails/domains/IPs.
- Misuse reports from the public (Grievance page) land here and in Support.

## 11. Voices, styles, pronunciations
Enable/disable voices and styles, display names, descriptions, tags (gender, accent, tone), order, "new" badge, sample regeneration button; plan restrictions per voice (future premium voices). Global pronunciation dictionary with ▶ test. Voice Lab candidates can be promoted to live voices from here once the owner approves them.

## 12. API & usage
All API keys across users (owner, created, last used, requests 24h/30d, revoke), per-key and per-user rate-limit overrides, top consumers, error rates by endpoint, OpenAPI docs link (admin-only view).

## 13. Queue & jobs
Live queue (position, user, chars, voice, waiting time), running job with progress, cancel job (refunds reserved characters), retry failed job, history of failures with error, throughput chart, average real-time factor. Pause queue / maintenance mode (shows a friendly banner to users; step-up).

## 14. System health & logs
CPU, RAM (voice-api RSS), disk, swap n/a, load, uptime, PM2 process status (restart button, step-up), MariaDB and Redis status, SSL certificate expiry for aiwazz.in / login.aiwazz.in / mail.aiwazz.in, mail queue size and last deliverability check (SPF/DKIM/DMARC records present), last backup time and size, storage used by audio + next cleanup run. Log viewer (API errors/warnings, filter by level/time/request ID; secrets redacted). Alerts (email to admin) for: API down, disk > 85%, RAM pressure, SSL < 14 days, mail queue stuck, webhook failures, backup failed.

## 15. Backups
Daily encrypted backup of the database + legal/config (not audio) with 14-day retention, stored on the server outside web roots and optionally copied off-server later. Admin page shows status and lets the owner download the latest (step-up). Restore procedure documented in `docs/RESTORE.md` (tested once).

## 16. Email
Templates (welcome, invite, verify email, password reset, payment receipt, payment failed, plan changed, subscription cancelled, account deleted, support reply, grievance acknowledgement) with brand layout, editable subject/body with variables and live preview, test-send. Sending log (to, template, status, message ID, bounces). Suppression list (hard bounces, unsubscribes).

## 17. Announcements & changelog
In-app banner (info/warning, audience: all / plan / admins, schedule start/end), and a public changelog page (`aiwazz.in/changelog/`) managed from admin (markdown, publish date).

## 18. Compliance (DPDP + legal)
Data-subject requests (access/export, correction, deletion, grievance) with due dates and status; one-click user data export (JSON + audio links still valid); consent records (signup consent, terms version, marketing opt-in) searchable; deletion log; policy version history (when legal pages changed). Company/legal data editor for `legal/legal.json` with schema validation, diff preview and rebuild (step-up, audited).

## 19. Settings
General (product name, support email, signup mode), limits (max characters per generation, queue per user, retention days), feature flags (referrals, open signup, premium voices, Hinglish default), payments mode TEST/LIVE (switching to LIVE needs step-up and a checklist: keys set, webhook verified, test payment done), security (session timeouts, admin IP allowlist), integrations status (Razorpay, mail).

## 20. Team & roles
Invite staff by email with a role, 2FA enforced on first login, change role (owner only), deactivate staff, last activity, per-staff audit trail.

## Build order (commit + push + deploy + report after each)
A1 security foundation + layout + audit · A2 overview + users + invites/waitlist · A3 billing (subscriptions, payments, refunds, invoices, dunning, webhooks log, GST exports) + plans + coupons · A4 support inbox + moderation · A5 voices/styles/pronunciations + API & usage + queue · A6 system health, logs, alerts, backups · A7 email templates, announcements/changelog, compliance, settings, team & roles · A8 analytics (metrics_daily + charts) + polish, Lighthouse ≥ 95 and a full test pass.

## Tech notes
- API: `/api/admin/*` FastAPI routers with a `require_perm("users.write")`-style dependency; Pydantic schemas; Alembic migrations for new tables (admin_audit, staff_roles, totp_secrets, backup_codes, notes, tags, coupons, webhook_events, email_templates, email_log, announcements, moderation_rules, flags, dsr_requests, metrics_daily, feature_flags, settings).
- Dashboard: React routes under `/admin`, lazy-loaded; TanStack Table for lists; charts with a lightweight library (Recharts or visx) loaded only in admin; forms with zod validation.
- Background work: small scheduler inside the API process or PM2 cron app (`aiwazz-cron`) for metrics, dunning, backups, cleanup, alerts; each task idempotent and logged.
- Tests for every permission (each role allowed/denied per endpoint), step-up, audit writes, refunds/credit notes, GST export totals.
- Never weaken existing security rules in CLAUDE.md.

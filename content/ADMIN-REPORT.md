# Admin panel (phase 12): morning report, 25 Nov 2026

**Panel:** https://login.aiwazz.in/admin, built from `content/ADMIN-PANEL.md` in order A1 to A8. Each step was
committed, pushed and deployed, and tested live through nginx with a temporary owner account.
Results:
- API tests: 164 passing.
- Both sites return 200.
- Lighthouse (mobile): 99–100 in all four categories on aiwazz.in `/`, `/pricing/`, `/changelog/`, `/grievance/`,
  `/contact/`, and on login.aiwazz.in `/login` and `/signup`.

The temporary accounts (`tmp-owner-a1@`, `tmp-user-a1@`) are deleted. **admin@aiwazz.in is now the owner and is the
only account.** Your /admin stays locked until you set up 2FA (below).

## 1. Set up your 2FA (5 minutes)

1. Install an authenticator app on your phone: Google Authenticator, Microsoft Authenticator, 1Password or Aegis.
2. Sign in at https://login.aiwazz.in, then open **https://login.aiwazz.in/admin** (also in the avatar menu → Admin panel).
3. Enter your account password, scan the QR code, and type the 6-digit code.
4. **Save the 10 backup codes** (Copy or Download) in your password manager. They are shown only once.
5. From then on: /admin asks for a code when you open it and after 30 minutes without activity. Sensitive actions ask
   for your password + a code again; that confirmation stays valid for 10 minutes. Covered actions: refunds, plan and
   price changes, roles, deleting users, exports, legal data, maintenance, backups download.

Lost your phone and all backup codes? On the server run `cd /www/aiwazz/api && .venv/bin/python manage.py reset-2fa --email admin@aiwazz.in`.

**Also do this today:** copy the backup passphrase from
`/root/aiwazz-backups/PASSPHRASE-copy-to-password-manager-then-delete.txt` into your password manager, then delete that
file. You need the passphrase to restore a backup if the server is lost (see `docs/RESTORE.md`).

## 2. What's done

| Step | What you get | Where |
|---|---|---|
| **A1** security | **Roles:** owner / admin / support / finance / viewer, checked on every endpoint (an automatic test covers every role × every route). **Non-staff:** plain 404. **2FA:** TOTP is mandatory; secrets are encrypted and codes can't be replayed; 10 hashed backup codes. **Step-up:** password + 2FA, valid 10 min. **Audit log:** append-only; the database itself refuses UPDATE/DELETE. **Sessions:** 30-min idle lock, "lock other admin sessions". **IP allowlist:** off; it won't let you lock yourself out. | Settings → Security, Audit log |
| **A2** overview, users, invites | **Overview:** KPIs with trends, charts, latest lists, ⌘K search, notifications bell. **Users:** list with filters, saved views, column chooser and CSV. **User detail** (11 tabs) and actions: plan + end date, bonus characters, suspend, emailed password reset, sessions, API keys, notes, tags, DPDP export, delete, read-only "view as user" (15 min, banner), bulk actions. **Privacy rule:** a user's scripts and audio need a stated reason to view, and every view is audited. **Invites:** plan + end date for early-access friends; waitlist approve/decline/bulk approve; signup mode. | Overview, Users, Invites & waitlist |
| **A3** billing | **Subscriptions:** cancel at period end or now, pause/resume, change plan (**upgrade now with proration, downgrade at period end**). **Payments:** includes failed ones, GST split. **Refunds:** full or partial; a credit note `AWZ-CN/<FY>/<n>` is issued automatically. **Invoices:** download PDF, regenerate (never renumbered), void with a credit note. **Dunning:** grace period of 7 days, emails on days 0/3/7, then the account goes to Free. **Webhook log:** includes bad signatures; failed events are re-run on Razorpay's retry; replay button. **GST report:** CSV/Excel with register, B2B, B2C by state, SAC summary, credit notes, payments for TDS. **Plans & pricing editor:** diff preview, commits `legal.json`, rebuilds the pricing page, creates new Razorpay plan versions; existing subscribers keep their price. **Coupons** and **referral settings** (referrals off). Usage now resets on the billing date for paid plans and on the 1st (IST) for Free. | Subscriptions, Payments, Invoices, Plans & pricing, Coupons |
| **A4** support, moderation | **Inbox:** contact form, invite requests, grievances and misuse reports in one place, with status, assignee, priority, internal notes, canned replies and replies threaded by Message-ID. **Grievances:** acknowledge-by-24 h and resolve-by-15-days timers, overdue view, automatic acknowledgement email. **Moderation:** rules (keywords or regex; flag or block) run on every script, plus volume-spike and many-accounts-per-IP flags. **Flag queue:** dismiss, warn, suspend, delete audio, note. **Blocklist:** email, domain or IP. **Landing:** the contact form has a topic field; the grievance page now has the form. | Support inbox, Moderation |
| **A5** product | **Voices & styles:** on/off, name, description, tags, order, "new" badge, plan per voice, sample regeneration; you can promote a studio voice (owner only). **Voice Lab / custom-voice pages:** now open only from an unlocked admin session. **Global pronunciations:** with ▶ test. **API & usage:** every key with 24 h / 30 d request counts, rate limits (default 60/min, overrides per key or user), top consumers, per-endpoint error rates, API docs. **Queue:** live queue, cancel (reserved characters are freed), retry, failures, throughput, real-time factor, pause queue / maintenance mode with a banner in the app. | Voices & styles, Pronunciations, API & usage, Queue & jobs |
| **A6** ops | **System health:** CPU, RAM, voice-api memory, disk, PM2 with restart, MariaDB, Redis, SSL expiry, mail and DNS records, storage. **Logs:** secrets redacted; every response has an X-Request-ID you can search for. **Alerts** every 5 min (bell + email to owner/admins). **Watchdog:** a new PM2 process, `aiwazz-watchdog`. **Backups:** daily, encrypted, kept 14 days; verify and download buttons. The first backup was made, decrypted and checked live. | System health, Logs |
| **A7** comms, governance | **Email:** 15 templates with a live preview, test send, sending log and suppression list. **In-app banners:** by audience and schedule. **Changelog:** public page at https://aiwazz.in/changelog/. **Compliance:** DPDP requests with due dates, consent records, deletion log, policy history, and an editor for the company data in `legal.json`. **Settings:** general, limits, feature flags, a **payments go-live checklist**, integrations status. **Team & roles:** invite staff, change role, deactivate, reset 2FA, transfer ownership. | Email, Announcements, Compliance, Settings, Team & roles |
| **A8** analytics | Nightly `metrics_daily` table plus live numbers for today. Date range with compare. Funnel from landing visit to signup to first voiceover to payment; visits come from your own nginx log, with no trackers and no stored IPs. Weekly cohorts, popularity charts, Hinglish usage, API vs web, revenue by plan and by state. Final polish and a visual check of every page on desktop and phone. | Analytics |

The global pronunciation list and the Voice Lab / custom-voice preview pages are now inside /admin (A5), as you asked.
Every billing decision you gave is in place. The SAC code is still the placeholder 998439 (shown in the GST report).

## 3. Blocked / not done (needs you or outside services)

- **Razorpay test keys** (pending from you): no real payment, refund, plan change or webhook ran against Razorpay
  yet. All of it is tested with a fake Razorpay (164 tests). Once the keys are set:
  1. Run `manage.py set-secret …` and `billing-create-plans`.
  2. Run one test payment and one refund.
  3. Open Settings → Payments: the checklist turns green.
- **Plan changes and UPI AutoPay:** Razorpay allows changing a subscription's plan only for card mandates. With UPI
  AutoPay the panel shows a clear message (cancel, then subscribe again).
- **Coupons:** Razorpay has no API to create discount offers. Create each offer in the Razorpay Dashboard and paste
  its `offer_…` id into the coupon.
- **Mail** (DNS + deliverability test pending): mail is off, so every email (invites, receipts, alerts, support
  replies, dunning) is **logged as "disabled"** in Email → Sending log. Nothing is lost; turn on `AIWAZZ_MAIL_ENABLED`
  after the test. Until then:
  - "Email password reset link" refuses with a clear message.
  - Invite codes are shown once in the panel so you can share them by hand.
  - Inbound replies and bounces aren't processed: there is no mail server yet. Add bounces to the suppression list by
    hand.
  - DKIM shows "no record (default._domainkey)". Set your selector in the API (`PUT /api/admin/settings/mail`) once
    the mail server gives you one.
- **Full restore test into a scratch database:** not run, because creating a second database needs your OK. A backup
  was decrypted and its dump checked complete (all tables). Steps for the full test are in `docs/RESTORE.md`.
- **Off-server backup copy:** "optionally later" in the spec; not set up.
- **Signup page in "open" mode:** the API supports it, but the signup page still shows "Request an invite" by
  default. If you ever open signups, the page needs a small change.
- **"Resend verification":** shown as n/a, since invite-only signup has no email verification. It comes with public
  signup later.
- **Trial → paid:** shown as n/a, because there are no trials (early access uses a time-limited plan).
- **Referrals:** the data model and settings exist, but the user-facing part isn't built; the feature flag is off,
  as specified.
- **LLPIN:** still pending from you. Add it in Compliance → Company data.

## 4. Decisions for you

1. **Moderation rules:** the 4 default rules (impersonating officials/banks, OTP/KYC scams, threats, explicit) only
   **flag** jobs for review. Do you want OTP/KYC scam phrases to **block** the job instead? Moderation → Rules.
2. **Grievance / DPDP timelines:** grievances are acknowledged within 24 h and resolved within 15 days. Other DPDP
   requests (access, correction, deletion) are due in 30 days. Is 30 days OK? It's my default; the Act sets no fixed
   number.
3. **Audit log retention:** the log keeps the email of a deleted user's account in its entries, for security records.
   Keep that, or remove emails after N years?
4. **Backups include `api/.env`** (encrypted), so a restore brings every key back. The alternative is to back up
   `.env` separately.
5. **Studio voice Veer:** promote it to everyone (Voices & styles → Promote, owner only) when you're ready. Remember
   the Learn guide and pricing note.
6. **Default API rate limit** is 60 requests per minute per key. OK?
7. **Who receives system alerts:** the owner and all admins. A separate ops address instead?

## 5. Changes outside the admin pages

- **Customers can now:**
  - change plan themselves in Settings → Billing (upgrades immediately with proration, downgrades at renewal);
  - enter a coupon at checkout;
  - see "new" badges and "<plan> plan" hints on voice cards;
  - see maintenance and announcement banners;
  - use the reset-password page at `/reset-password`.
- **Staff** see "Admin panel" in the avatar menu.
- **New PM2 process:** `aiwazz-watchdog` (runs every 5 minutes, then exits; "stopped" between runs is normal).
  `pm2 save` was run.
- **New migrations on `aiwazz_voice`:** `a8b1…` to `a7b8…` (8 in total). A database backup from before the first
  migration is in `/root/project-backups/aiwazz-pre-admin-2026-11-24/`.
- **New Python packages:** pyotp, segno, cryptography, openpyxl.
- **New npm packages** (admin bundle only, lazy-loaded): @tanstack/react-table 8, recharts, zod.
- **No changes to:** nginx, firewall, SSH, panel or DNS, and no other sites.

## 6. Owner decisions applied (25 Nov 2026)

1. **Moderation:** "OTP / KYC scam phrases" and "Impersonating officials or banks" now **block** the job. The user
   sees a clear Acceptable Use message, nothing is counted, and a "blocked" flag appears in the queue. "Threats" and
   "Explicit content" still only flag.
2. **DPDP requests:** 30-day deadline kept.
3. **Audit log:** a deleted account's email stays for 3 years after the deletion, then a daily sweep
   (`admin/audit_redact.py`, task `audit-redact`) replaces it with `sha256:<hash>`. That is the same hash as the
   deletion log, so you can still match it when someone gives you their email. Emails with no deletion record count
   from the audit entry's own date.
   - The database trigger still refuses every edit, except this redaction. The sweep marks its own connection, and
     only the label, email, reason and before/after fields may change. Deleting rows is still refused.
   - Tested in `tests/test_owner_decisions.py`.
4. **Backups:** the encrypted `api/.env` stays in them.
5. **Veer:** stays owner-only.
6. **API limit:** 60 requests per minute per key.
7. **Alerts:** emails go to the owner only. System health shows a red banner, "Email alerts are not being sent",
   while mail is disabled.

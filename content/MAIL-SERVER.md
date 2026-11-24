# Self-hosted mail for aiwazz.in (phase 11)

Owner decision: **own mail server on this VPS, no third-party email service.**

## Design
- Postfix (SMTP) + Dovecot (IMAP) via aaPanel's **Mail Server** app (owner installs it from the App Store). Rspamd for spam/DKIM signing.
- **Do not install ClamAV** (antivirus uses ~1 GB RAM; we need RAM for Kokoro). If aaPanel enables it, turn it off.
- Mail hostname: **mail.aiwazz.in**. Set Postfix `myhostname = mail.aiwazz.in` explicitly (the system hostname may reset to cloudwablaster on reboot on OpenVZ; mail must not depend on it).
- Mailboxes: `support@aiwazz.in` (support + legal contact), `noreply@aiwazz.in` (app sending), `admin@aiwazz.in` (owner/admin account, DMARC reports).
- The app sends through local Postfix: `127.0.0.1:587`, STARTTLS, user `noreply@aiwazz.in`, password only in `api/.env` (`AIWAZZ_SMTP_*`). Never relay for anyone else (no open relay).
- TLS: Let's Encrypt certificate for mail.aiwazz.in used by Postfix and Dovecot.

## Before anything: check that sending can work at all
1. Outbound port 25: `timeout 10 bash -c '</dev/tcp/gmail-smtp-in.l.google.com/25' && echo OPEN || echo BLOCKED`. Many VPS providers block it; if BLOCKED, the owner must ask the provider to unblock port 25. Stop and report.
2. IP reputation: check 104.237.6.214 on major blocklists (Spamhaus, Barracuda, SpamCop via DNS lookups). Report any listing.
3. Reverse DNS (PTR): `dig -x 104.237.6.214 +short` must return `mail.aiwazz.in`. Only the VPS provider can set this; report the current value.

## DNS records the owner adds at the DNS provider
| Type | Name | Value |
|---|---|---|
| A | mail | 104.237.6.214 |
| MX | @ (aiwazz.in) | mail.aiwazz.in (priority 10) |
| TXT | @ | `v=spf1 ip4:104.237.6.214 mx -all` |
| TXT | `<selector>._domainkey` | DKIM public key generated on the server (give the owner the exact value) |
| TXT | _dmarc | `v=DMARC1; p=none; rua=mailto:admin@aiwazz.in; fo=1` (move to `p=quarantine` after 2–4 weeks of clean reports) |
| PTR | 104.237.6.214 | mail.aiwazz.in (ask the VPS provider) |

## Firewall (owner approves; Claude Code applies only with explicit OK)
Open: 25 (SMTP in/out), 587 (submission), 465 (SMTPS), 993 (IMAPS). Keep 110/143/995 closed (plain or unneeded).

## App features to wire once mail works
- Contact form → email to support@aiwazz.in (keep saving to DB too).
- Forgot password: single-use token (SHA-256 in DB), 30-minute expiry, rate-limited, same response whether or not the email exists.
- Email verification on signup (later, when signup opens).
- Account deletion confirmation email with reference number.
- Plain-text + simple HTML templates in the brand style, sender "AiWazz <noreply@aiwazz.in>", Reply-To support@aiwazz.in, List-Unsubscribe header on any non-transactional email.
- Update `legal/legal.json`: supportEmail / privacyEmail / grievance email → support@aiwazz.in **after** the inbox is confirmed working.

## Deliverability test (must pass before using it for users)
- https://www.mail-tester.com score ≥ 9/10.
- Send to a Gmail and an Outlook address: lands in Inbox, "mailed-by" and "signed-by" show aiwazz.in, SPF/DKIM/DMARC = PASS in "Show original".
- Register aiwazz.in in Google Postmaster Tools.
- Warm-up: low volume for the first 2–4 weeks; new IPs are distrusted at first.

## Pre-check results (24 Nov 2026)
| Check | Result |
|---|---|
| Outbound port 25 | **OPEN** (`220 mx.google.com ESMTP` banner received) |
| Blocklists for 104.237.6.214 | **Not listed**: Spamhaus ZEN (queried at Spamhaus' own NS; Google DNS is refused by Spamhaus), Barracuda, SpamCop, SORBS, PSBL, Mailspike, UCEPROTECT-1, s5h. aiwazz.in not on Spamhaus DBL |
| PTR 104.237.6.214 | **Empty**. IP belongs to **Hosteros LLC**: ask them to set rDNS → `mail.aiwazz.in` |
| Existing DNS (Hostinger, ns*.dns-parking.com) | MX `mx1/mx2.hostinger.com`, SPF `include:_spf.mail.hostinger.com ~all`, DMARC `p=none`. These must be **replaced** (not added to): one SPF record per domain, and the MX change moves all incoming @aiwazz.in mail to this VPS |
| Firewall (ufw) | open: 22, 80, 443, 21833. Mail ports closed until the owner confirms the install |
| RAM | ~4 GB available; Postfix + Dovecot + Rspamd ≈ 200–300 MB without ClamAV |

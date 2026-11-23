---
slug: /data-deletion/
title: Data Deletion Instructions
metaTitle: Data Deletion Instructions | AiWazz
metaDescription: How to delete your AiWazz account and personal data, including data received through Google or Meta sign-in. Confirmed within 30 days.
---

# Data Deletion Instructions

You can ask **{{legalName}}** (AiWazz) to delete your account and personal data at any time. This page applies to all AiWazz users, including anyone who signed in or connected through a third-party platform such as Google, Facebook or WhatsApp (Meta).

## Option 1: Delete in the app (instant)

1. Sign in at {{websites.app}}.
2. Go to **Settings → Account**.
3. Click **Delete account**, type `DELETE` to confirm, and press **Delete permanently**.

Your account is closed immediately and your data is erased within 30 days.

## Option 2: Request by email

Send an email to **{{privacyEmail}}** from your registered email address with the subject **"Delete my data"**. If you signed in with a third-party platform, include the name or email shown on that account.

We will:

1. Acknowledge your request within 3 business days.
2. Verify that the request comes from the account owner.
3. Delete your data within 30 days and email you a confirmation with a reference number.

## If you connected a Meta (Facebook or WhatsApp) account

You can also remove AiWazz from your Facebook account under **Settings & privacy → Settings → Apps and websites → AiWazz → Remove**. When you do, we delete the data we received from Meta about you within 30 days.

<!-- Implementation: if Meta login is ever added, implement the Meta Data Deletion Request Callback at https://login.aiwazz.in/api/meta/data-deletion (verify signed_request, queue deletion, return {url, confirmation_code}) and a status page at https://aiwazz.in/data-deletion/status/?code=XXXX. -->

## What gets deleted

- Account details (name, email, password hash), settings and API keys.
- Scripts, generation history and audio files.
- Data received from third-party sign-in platforms.

## What we keep, and why

- **Payment and GST invoice records:** kept for 8 years because Indian tax law requires it. They are used for no other purpose.
- **Security logs:** kept for up to 90 days to prevent fraud, then deleted.

## Questions

Email {{privacyEmail}} or contact our Grievance Officer, {{grievanceOfficer.name}}, at {{grievanceOfficer.email}}. See our [Privacy Policy](/privacy/) for more.

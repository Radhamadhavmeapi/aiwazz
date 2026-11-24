# Restoring AiWazz from a backup

Backups are made by the API every day after 02:00 IST (admin → System health → Backups shows them; "Back up now"
makes one immediately). Each file is `/root/aiwazz-backups/aiwazz-<YYYYMMDD-HHMM>.tar.gz.enc` (root only, 14 days kept).

**What is inside** (AES-256-CBC, PBKDF2 200 000 rounds, `openssl enc`):

| File | What |
|---|---|
| `aiwazz_voice.sql` | full `mysqldump --single-transaction --routines --triggers` of the `aiwazz_voice` database |
| `MANIFEST.json` | when, which database, which files |
| `legal/legal.json`, `ecosystem.config.js`, `deploy/nginx/*.conf` | company data, PM2 and nginx config |
| `api/.env` | secrets (DB password, Razorpay, 2FA encryption key, backup passphrase) |
| `data/voices/*/voice.json` | studio voice definitions (reference audio is not in the backup) |

Not included: generated audio (kept 7 days anyway), Kokoro/OpenVoice model files (re-downloadable), the code (GitHub).

**You need the passphrase** (`AIWAZZ_BACKUP_PASSPHRASE`). It is in `api/.env`, and you must keep a copy outside the
server (password manager): if the server is lost, `.env` is lost with it. `manage.py gen-backup-key` left a copy in
`/root/aiwazz-backups/PASSPHRASE-copy-to-password-manager-then-delete.txt` the first time; copy it, then delete that file.

## 1. Decrypt and unpack (safe, changes nothing)

```bash
mkdir -m 700 /root/restore && cd /root/restore
read -rs AIWAZZ_BACKUP_PASSPHRASE && export AIWAZZ_BACKUP_PASSPHRASE      # paste the passphrase (hidden)
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in /root/aiwazz-backups/aiwazz-YYYYMMDD-HHMM.tar.gz.enc \
  -out backup.tar.gz -pass env:AIWAZZ_BACKUP_PASSPHRASE
tar -xzf backup.tar.gz && cat MANIFEST.json && tail -1 aiwazz_voice.sql        # must end with "-- Dump completed"
```

(admin → System health → "Verify latest" does exactly this check automatically.)

## 2. Restore the database

**Stop the API first** so nothing writes while you restore:

```bash
pm2 stop voice-api aiwazz-watchdog
# Optional safety copy of the current state:
mysqldump --defaults-extra-file=<(printf "[client]\nuser=aiwazz_voice\npassword=%s\n" "$DBPASS") aiwazz_voice > /root/restore/before-restore.sql
# Restore (the dump drops and recreates every table, including the audit-log triggers):
mysql -u aiwazz_voice -p aiwazz_voice < /root/restore/aiwazz_voice.sql
cd /www/aiwazz/api && .venv/bin/alembic current        # should show the head revision of the restored code
.venv/bin/alembic upgrade head                         # if the code is newer than the backup
pm2 start voice-api aiwazz-watchdog
```

On a **new server**, first create the database and its user (aaPanel → Databases, or
`CREATE DATABASE aiwazz_voice CHARACTER SET utf8mb4; CREATE USER 'aiwazz_voice'@'localhost' IDENTIFIED BY '…';
GRANT ALL ON aiwazz_voice.* TO 'aiwazz_voice'@'localhost';`), clone the repo to `/www/aiwazz`, then copy `api/.env`
from the backup (chmod 600) before step 2. Then follow README.md for the venv, models and PM2.

## 3. Config files

Compare before overwriting: `diff /root/restore/legal/legal.json /www/aiwazz/legal/legal.json` (legal.json is also in
git, so usually nothing to do). nginx files go to `/www/server/panel/vhost/nginx/extension/<site>/aiwazz.conf`; always
`nginx -t` before `nginx -s reload`.

## 4. Check

- https://login.aiwazz.in/api/health → `{"status":"ok"}`; sign in; admin → System health shows no alerts.
- admin → Audit log has the latest entries from before the backup.
- Delete `/root/restore` when done (`rm -r /root/restore`): it holds an unencrypted database copy.

## Tested

24 Nov 2026: a backup was made on the live server, decrypted with the passphrase and unpacked; the dump ended with
`-- Dump completed` and contained every table (`verify_backup`, same as "Verify latest"). A full restore into a
scratch database was **not** run, because creating another database needs the owner's OK; to test it end to end,
create `aiwazz_restore_test` (owner), run step 2 against it, compare row counts, then drop it.

"""System health, alerts, logs and backups for the admin panel (A6).

Everything is read-only except: PM2 restart (step-up), backups (scheduled daily + on demand). Commands run as
subprocesses with argument lists (no shell). Secrets never leave the server: logs are redacted before display.
"""
import asyncio
import json
import os
import re
import shutil
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from settings import API_DIR, get_settings

from . import settings_store

PM2 = "/www/server/nodejs/v24.11.1/bin/pm2"
NODE_PATH = "/www/server/nodejs/v24.11.1/bin"
BACKUP_DIR = Path(os.environ.get("AIWAZZ_BACKUP_DIR", "/root/aiwazz-backups"))
BACKUP_RETENTION_DAYS = 14
LOG_DIR = API_DIR / "storage" / "logs"
SSL_HOSTS = ("aiwazz.in", "login.aiwazz.in", "mail.aiwazz.in")
IST = timedelta(hours=5, minutes=30)
PROCESSES = ("voice-api", "voice-clone", "aiwazz-watchdog")


async def _run(*argv: str, timeout: float = 20, env: dict | None = None) -> tuple[int, str]:
    try:
        p = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                 env={**os.environ, "PATH": f"{NODE_PATH}:/usr/sbin:/usr/bin:/sbin:/bin", **(env or {})})
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
        return p.returncode or 0, out.decode("utf-8", "replace")
    except (FileNotFoundError, TimeoutError) as e:
        return 127, str(e)


# ── Metrics ──────────────────────────────────────────────────────────────────
def _meminfo() -> dict[str, int]:
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        out[k] = int(v.split()[0]) * 1024
    return out


def _rss(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _cpu_percent(interval: float = 0.3) -> float:
    def snap():
        parts = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return sum(parts), idle
    t1, i1 = snap()
    time.sleep(interval)
    t2, i2 = snap()
    return round(100 * (1 - (i2 - i1) / max(1, t2 - t1)), 1)


def _dir_size(p: Path) -> tuple[int, int]:
    total = n = 0
    if p.is_dir():
        for f in p.iterdir():
            if f.is_file():
                total += f.stat().st_size
                n += 1
    return total, n


async def pm2_status() -> list[dict]:
    code, out = await _run(PM2, "jlist")
    try:
        start = out.index("[")
        data = json.loads(out[start:])
    except (ValueError, json.JSONDecodeError):
        return []
    rows = []
    for p in data:
        env = p.get("pm2_env", {})
        rows.append({"name": p.get("name"), "status": env.get("status"), "restarts": env.get("restart_time", 0),
                     "uptime_sec": int(time.time() - env.get("pm_uptime", time.time() * 1000) / 1000) if env.get("status") == "online" else 0,
                     "memory": (p.get("monit") or {}).get("memory", 0), "cpu": (p.get("monit") or {}).get("cpu", 0),
                     "ours": p.get("name") in PROCESSES})
    return rows


def ssl_expiry(host: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock, ctx.wrap_socket(sock, server_hostname=host) as s:
            cert = s.getpeercert()
        end = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        return {"host": host, "ok": True, "expires_at": end.isoformat() + "Z", "days_left": (end - utcnow()).days}
    except (OSError, ssl.SSLError, KeyError, ValueError) as e:
        return {"host": host, "ok": False, "error": str(e)[:120], "days_left": None}


async def mail_status(db: AsyncSession) -> dict:
    code, out = await _run("postqueue", "-p", timeout=10)
    if code == 127:
        queue = {"installed": False, "size": None}
    else:
        m = re.search(r"in (\d+) Request", out)
        queue = {"installed": True, "size": int(m.group(1)) if m else 0}
    cfg = await settings_store.get(db, "mail")
    dns = {}
    for name, q in (("spf", "aiwazz.in"), ("dmarc", "_dmarc.aiwazz.in"), ("dkim", f"{cfg.get('dkim_selector', 'default')}._domainkey.aiwazz.in")):
        c, o = await _run("dig", "+short", "TXT", q, timeout=8)
        txt = o.strip()
        dns[name] = bool(txt) and {"spf": "v=spf1", "dmarc": "v=DMARC1", "dkim": "p="}[name] in txt
    return {"enabled": get_settings().mail_enabled, "queue": queue, "dns": dns, "dkim_selector": cfg.get("dkim_selector", "default"),
            "checked_at": utcnow().isoformat() + "Z"}


async def db_status(db: AsyncSession) -> dict:
    try:
        if db.bind.dialect.name == "mysql":
            version = (await db.execute(text("SELECT VERSION()"))).scalar()
            uptime = (await db.execute(text("SHOW GLOBAL STATUS LIKE 'Uptime'"))).one()[1]
            size = (await db.execute(text("SELECT COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables "
                                          "WHERE table_schema = DATABASE()"))).scalar()
            return {"ok": True, "version": version, "uptime_sec": int(uptime), "size_bytes": int(size or 0)}
        await db.execute(text("SELECT 1"))
        return {"ok": True, "version": db.bind.dialect.name, "uptime_sec": None, "size_bytes": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


async def redis_status(redis) -> dict:
    try:
        t = time.perf_counter()
        await redis.ping()
        ping = round((time.perf_counter() - t) * 1000, 1)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    try:
        used = (await redis.info("memory")).get("used_memory_human")
    except Exception:  # noqa: BLE001
        used = None
    return {"ok": True, "ping_ms": ping, "used_memory": used}


async def collect(app, db: AsyncSession) -> dict:
    s = get_settings()
    mem = _meminfo()
    disk = shutil.disk_usage("/")
    load1, load5, load15 = os.getloadavg()
    audio_bytes, audio_files = _dir_size(s.audio_dir)
    cpu = await asyncio.to_thread(_cpu_percent)
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    from models import TaskRun
    last_cleanup = None   # cleanup runs inside the job manager every hour (tts/jobs.cleanup_loop)
    backups = list_backups()
    watchdog = read_watchdog()
    ssl_info = await asyncio.gather(*(asyncio.to_thread(ssl_expiry, h) for h in SSL_HOSTS))
    last_backup_run = (await db.execute(select(TaskRun).where(TaskRun.task == "backup").order_by(TaskRun.id.desc()).limit(1))).scalars().first()
    return {
        "host": {"cpu_percent": cpu, "cores": os.cpu_count(), "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
                 "uptime_sec": int(uptime), "memory_total": mem.get("MemTotal"), "memory_available": mem.get("MemAvailable"),
                 "swap": "n/a (OpenVZ container, no swap)", "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free,
                 "disk_percent": round(disk.used / disk.total * 100, 1)},
        "api": {"pid": os.getpid(), "rss": _rss(os.getpid()), "engine_ready": app.state.jobs.engine.ready,
                "queue": len(app.state.jobs.pending)},
        "processes": await pm2_status(), "database": await db_status(db), "redis": await redis_status(app.state.redis),
        "ssl": list(ssl_info), "mail": await mail_status(db),
        "storage": {"audio_bytes": audio_bytes, "audio_files": audio_files, "retention_days": s.audio_retention_days,
                    "cleanup": "hourly (files older than the retention period)", "last_cleanup": last_cleanup},
        "backups": {"dir": str(BACKUP_DIR), "count": len(backups), "latest": backups[0] if backups else None,
                    "last_run": {"status": last_backup_run.status, "started_at": last_backup_run.started_at.isoformat() + "Z",
                                 "detail": last_backup_run.detail} if last_backup_run else None,
                    "retention_days": BACKUP_RETENTION_DAYS, "encrypted": bool(s.backup_passphrase)},
        "watchdog": watchdog,
        "alerts": await active_alerts(db),
    }


# ── Alerts ───────────────────────────────────────────────────────────────────
def read_watchdog() -> dict | None:
    p = API_DIR / "storage" / "watchdog.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


async def evaluate(app, db: AsyncSession) -> list[dict]:
    """Current problems. Each: {key, level, title, detail}."""
    from models import TaskRun, WebhookEvent
    out = []
    disk = shutil.disk_usage("/")
    pct = disk.used / disk.total * 100
    if pct > 85:
        out.append({"key": "disk", "level": "danger" if pct > 92 else "warning", "title": f"Disk {pct:.0f}% full",
                    "detail": f"{disk.free / 1e9:.1f} GB free"})
    mem = _meminfo()
    if mem.get("MemAvailable", 1) / max(1, mem.get("MemTotal", 1)) < 0.12:
        out.append({"key": "ram", "level": "warning", "title": "Memory pressure",
                    "detail": f"{mem['MemAvailable'] / 1e9:.1f} GB available of {mem['MemTotal'] / 1e9:.1f} GB (no swap)"})
    for info in await asyncio.gather(*(asyncio.to_thread(ssl_expiry, h) for h in SSL_HOSTS[:2])):
        if info["days_left"] is not None and info["days_left"] < 14:
            out.append({"key": f"ssl-{info['host']}", "level": "danger" if info["days_left"] < 5 else "warning",
                        "title": f"SSL for {info['host']} expires in {info['days_left']} days", "detail": "aaPanel renews Let's Encrypt automatically; check it"})
        elif not info["ok"]:
            out.append({"key": f"ssl-{info['host']}", "level": "danger", "title": f"SSL check failed for {info['host']}", "detail": info.get("error", "")})
    wd = read_watchdog()
    if wd and wd.get("api_ok") is False:
        out.append({"key": "api-down", "level": "danger", "title": "API was down", "detail": f"watchdog: {wd.get('detail', '')}"})
    if get_settings().mail_enabled:
        code, o = await _run("postqueue", "-p", timeout=10)
        m = re.search(r"in (\d+) Request", o)
        if m and int(m.group(1)) > 20:
            out.append({"key": "mail-queue", "level": "warning", "title": f"Mail queue: {m.group(1)} messages waiting", "detail": "postqueue -p"})
    n = (await db.execute(select(func.count()).select_from(WebhookEvent).where(
        WebhookEvent.status == "failed", WebhookEvent.received_at >= utcnow() - timedelta(hours=24)))).scalar_one()
    if n:
        out.append({"key": "webhooks", "level": "warning", "title": f"{n} webhook event(s) failed in 24 h", "detail": "Payments → Webhooks"})
    last = (await db.execute(select(TaskRun).where(TaskRun.task == "backup").order_by(TaskRun.id.desc()).limit(1))).scalars().first()
    if last and last.status == "failed":
        out.append({"key": "backup", "level": "danger", "title": "Last backup failed", "detail": last.detail[:120]})
    elif get_settings().backup_passphrase:
        latest = list_backups()[:1]
        if not latest or datetime.fromisoformat(latest[0]["created_at"].rstrip("Z")) < utcnow() - timedelta(hours=26):
            out.append({"key": "backup-stale", "level": "warning", "title": "No backup in the last 26 hours", "detail": "System health → Backups"})
    return out


async def active_alerts(db: AsyncSession) -> list[dict]:
    return (await settings_store.get(db, "alerts.state")).get("active", [])


async def check_and_notify(app, db: AsyncSession) -> str:
    """Store the current alerts; email staff (owner + admins) when an alert starts or clears."""
    from emails import send_template
    from models import User
    current = await evaluate(app, db)
    state = await settings_store.get(db, "alerts.state")
    before = {a["key"] for a in state.get("active", [])}
    now = {a["key"] for a in current}
    started = [a for a in current if a["key"] not in before]
    cleared = [k for k in before if k not in now]
    if started or cleared:
        staff = (await db.execute(select(User.email).where(User.role.in_(("owner", "admin")), User.is_active.is_(True)))).scalars().all()
        lines = [f"PROBLEM: {a['title']} ({a['detail']})" for a in started] + [f"RESOLVED: {k}" for k in cleared]
        for email in staff:
            await send_template(db, "system_alert", email, {"summary": "; ".join(lines)[:150], "lines": "\n".join(lines)})
    await settings_store.put(db, "alerts.state", {"active": current, "checked_at": utcnow().isoformat() + "Z"}, None)
    await db.commit()
    return f"{len(current)} active, {len(started)} new, {len(cleared)} cleared"


# ── Logs ─────────────────────────────────────────────────────────────────────
_REDACT = [
    (re.compile(r"aiw_live_[A-Za-z0-9_\-]{6,}"), "aiw_live_[redacted]"),
    (re.compile(r"rzp_(live|test)_[A-Za-z0-9]{6,}"), r"rzp_\1_[redacted]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|x-clone-secret)([\"'=: ]+)([^\s\"',&]+)"), r"\1\2[redacted]"),
    (re.compile(r"mysql\+aiomysql://[^@\s]+@"), "mysql+aiomysql://[redacted]@"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [redacted]"),
]
_LINE = re.compile(r"^(?P<pm2>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d): (?:(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ )?(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)?:?\s*(?P<rest>.*)$")


def redact(s: str) -> str:
    for rx, rep in _REDACT:
        s = rx.sub(rep, s)
    return s


def read_logs(level: str = "", q: str = "", request_id: str = "", since: str = "", limit: int = 300, include_access: bool = False) -> list[dict]:
    """Newest first. Parses PM2-timestamped lines from voice-api.{out,err}.log (last ~4 MB of each)."""
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_level = order.get(level.upper(), 0)
    entries = []
    for name in ("voice-api.err.log", "voice-api.out.log"):
        p = LOG_DIR / name
        if not p.is_file():
            continue
        with p.open("rb") as f:
            f.seek(max(0, p.stat().st_size - 4_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()[1:]
        cur = None
        for raw in lines:
            m = _LINE.match(raw)
            if not m:
                continue
            rest = m.group("rest")
            lvl = m.group("level") or ""
            is_access = rest.startswith(("127.0.0.1", "104.237")) or ' HTTP/1.1" ' in rest
            if not lvl:
                if cur is not None and not is_access:        # continuation (traceback) of the previous entry
                    cur["message"] += "\n" + rest
                    continue
                lvl = "INFO"
            if is_access and not include_access:
                cur = None
                continue
            # PM2 stamps lines in the server's local time zone (not UTC): convert so the panel shows the right IST time.
            t = datetime.fromisoformat(m.group("pm2")).astimezone(UTC).replace(tzinfo=None).isoformat() + "Z"
            cur = {"time": t, "level": lvl, "message": rest, "source": name.split(".")[1]}
            entries.append(cur)
    out = []
    for e in sorted(entries, key=lambda e: e["time"], reverse=True):
        if order.get(e["level"], 20) < min_level:
            continue
        if since and e["time"] < since:
            continue
        e["message"] = redact(e["message"])[:4000]
        if q and q.lower() not in e["message"].lower():
            continue
        if request_id and request_id not in e["message"]:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# ── Backups ──────────────────────────────────────────────────────────────────
def list_backups() -> list[dict]:
    if not BACKUP_DIR.is_dir():
        return []
    rows = []
    for f in sorted(BACKUP_DIR.glob("aiwazz-*.tar.gz.enc"), reverse=True):
        st = f.stat()
        rows.append({"name": f.name, "size": st.st_size, "created_at": datetime.fromtimestamp(st.st_mtime, UTC).replace(tzinfo=None).isoformat() + "Z"})
    return rows


BACKUP_FILES = ["legal/legal.json", "ecosystem.config.js", "deploy/nginx/login.aiwazz.in.conf", "deploy/nginx/aiwazz.in.conf",
                "api/.env"]


async def make_backup() -> str:
    """mysqldump (consistent, routines + triggers) + legal/config files → tar.gz → AES-256 (openssl, PBKDF2) with
    AIWAZZ_BACKUP_PASSPHRASE. Audio is not backed up (kept 7 days). Keeps BACKUP_RETENTION_DAYS days."""
    from sqlalchemy.engine import make_url
    s = get_settings()
    if not s.backup_passphrase:
        raise RuntimeError("AIWAZZ_BACKUP_PASSPHRASE is not set (manage.py gen-backup-key)")
    BACKUP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    stamp = (utcnow() + IST).strftime("%Y%m%d-%H%M")
    work = BACKUP_DIR / f".work-{stamp}"
    work.mkdir(mode=0o700, exist_ok=True)
    final = BACKUP_DIR / f"aiwazz-{stamp}.tar.gz.enc"
    try:
        url = make_url(s.database_url)
        cnf = work / "my.cnf"
        cnf.write_text(f"[client]\nuser={url.username}\npassword={url.password}\nhost={url.host or '127.0.0.1'}\nport={url.port or 3306}\n")
        os.chmod(cnf, 0o600)
        dump = work / "aiwazz_voice.sql"
        with dump.open("wb") as fh:
            p = await asyncio.create_subprocess_exec("mysqldump", f"--defaults-extra-file={cnf}", "--single-transaction", "--routines",
                                                     "--triggers", "--hex-blob", url.database, stdout=fh, stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(p.communicate(), 600)
        if p.returncode != 0:
            raise RuntimeError(f"mysqldump failed: {err.decode()[:200]}")
        cnf.unlink()
        root = API_DIR.parent
        files = [f for f in BACKUP_FILES if (root / f).exists()]
        voices = [str(v.relative_to(root)) for v in (root / "data" / "voices").glob("*/voice.json")]
        manifest = {"created_at": utcnow().isoformat() + "Z", "database": url.database, "files": files + voices,
                    "alembic_head": None}
        (work / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
        tar = work / "backup.tar.gz"
        code, out = await _run("tar", "-czf", str(tar), "-C", str(work), "aiwazz_voice.sql", "MANIFEST.json",
                               "-C", str(root), *files, *voices, timeout=600)
        if code != 0:
            raise RuntimeError(f"tar failed: {out[-200:]}")
        code, out = await _run("openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-in", str(tar),
                               "-out", str(final), "-pass", "env:AIWAZZ_BACKUP_PASSPHRASE", timeout=600,
                               env={"AIWAZZ_BACKUP_PASSPHRASE": s.backup_passphrase})
        if code != 0:
            raise RuntimeError(f"openssl failed: {out[-200:]}")
        os.chmod(final, 0o600)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    removed = 0
    for f in BACKUP_DIR.glob("aiwazz-*.tar.gz.enc"):
        if f.stat().st_mtime < time.time() - BACKUP_RETENTION_DAYS * 86400:
            f.unlink()
            removed += 1
    return f"{final.name} ({final.stat().st_size / 1e6:.1f} MB), {removed} old removed"


async def verify_backup(path: Path) -> dict:
    """Decrypt to memory-free temp, list the archive and check the dump is complete (used by the restore test)."""
    s = get_settings()
    work = BACKUP_DIR / ".verify"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(mode=0o700)
    try:
        tar = work / "b.tar.gz"
        code, out = await _run("openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-in", str(path), "-out", str(tar),
                               "-pass", "env:AIWAZZ_BACKUP_PASSPHRASE", env={"AIWAZZ_BACKUP_PASSPHRASE": s.backup_passphrase})
        if code != 0:
            return {"ok": False, "error": "decrypt failed"}
        code, listing = await _run("tar", "-tzf", str(tar))
        await _run("tar", "-xzf", str(tar), "-C", str(work), "aiwazz_voice.sql")
        sql = (work / "aiwazz_voice.sql").read_text(errors="replace")
        return {"ok": "-- Dump completed" in sql[-300:], "files": listing.split(), "tables": sql.count("CREATE TABLE")}
    finally:
        shutil.rmtree(work, ignore_errors=True)

"""A6: system health, PM2 restart (step-up), log viewer (filters + redaction), alerts (start/clear emails), backups
(configured check, verify an encrypted archive, download needs step-up), request ids."""
import os
import subprocess
from collections import namedtuple

import pytest

from tests.conftest import run_db, stepup


@pytest.fixture
def offline(monkeypatch):
    """No network or PM2 in tests."""
    from admin import health

    async def fake_run(*argv, timeout=20, env=None):
        if argv[0] == health.PM2:
            return 0, '[{"name":"voice-api","pm2_env":{"status":"online","restart_time":1,"pm_uptime":0},"monit":{"memory":1,"cpu":0}}]'
        if argv[0] in ("postqueue", "dig"):
            return 127, ""
        return await real(*argv, timeout=timeout, env=env)
    real = health._run
    monkeypatch.setattr(health, "_run", fake_run)
    monkeypatch.setattr(health, "ssl_expiry", lambda h: {"host": h, "ok": True, "expires_at": None, "days_left": 60})
    return health


def test_system_overview(staff, offline):
    v = staff("viewer")
    d = v.get("/api/admin/system").json()
    assert d["host"]["disk_total"] > 0 and d["api"]["rss"] > 0 and d["processes"][0]["name"] == "voice-api"
    assert d["database"]["ok"] and d["redis"]["ok"] and d["mail"]["queue"]["installed"] is False
    assert d["host"]["swap"].startswith("n/a")
    assert v.get("/api/admin/logs").status_code == 403                   # viewer: no logs


def test_restart_needs_stepup_and_only_ours(staff, offline, clock):
    calls = []

    async def fake(*argv, timeout=20, env=None):
        calls.append(argv)
        return 0, ""
    offline._run = fake
    a = staff("admin")
    assert a.post("/api/admin/system/processes/voice-clone/restart", json={"reason": "stuck"}).status_code == 403
    stepup(a, clock)
    assert a.post("/api/admin/system/processes/nginx/restart", json={"reason": "nope"}).status_code == 404
    r = a.post("/api/admin/system/processes/voice-clone/restart", json={"reason": "stuck worker"})
    assert r.status_code == 200
    assert a.get("/api/admin/audit?action=system.process.restart").json()["total"] == 1


def test_logs_filter_and_redact(staff, monkeypatch, tmp_path):
    from admin import health
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    (tmp_path / "voice-api.out.log").write_text(
        "header\n"
        "2026-11-24T08:00:00: 2026-11-24 08:00:00,1 INFO voice-api [abc123]: started\n"
        "2026-11-24T08:01:00: 2026-11-24 08:01:00,1 WARNING aiwazz.billing [def456]: key aiw_live_SECRETSECRET used, password=hunter22\n"
        "2026-11-24T08:02:00: INFO:     127.0.0.1:0 - \"GET /api/health HTTP/1.1\" 200 OK\n")
    (tmp_path / "voice-api.err.log").write_text(
        "header\n2026-11-24T08:03:00: 2026-11-24 08:03:00,1 ERROR voice-api [ghi789]: boom\n2026-11-24T08:03:00: Traceback (most recent call last):\n"
        "2026-11-24T08:03:00:   File \"x.py\", line 1\n")
    a = staff("admin")
    items = a.get("/api/admin/logs").json()["items"]
    assert [i["level"] for i in items] == ["ERROR", "WARNING", "INFO"]                    # newest first, access log hidden
    assert "Traceback" in items[0]["message"]                                              # continuation lines joined
    assert "SECRETSECRET" not in items[1]["message"] and "hunter22" not in items[1]["message"]
    assert [i["level"] for i in a.get("/api/admin/logs?level=warning").json()["items"]] == ["ERROR", "WARNING"]
    assert len(a.get("/api/admin/logs?request_id=def456").json()["items"]) == 1
    assert len(a.get("/api/admin/logs?access=true").json()["items"]) == 4


def test_alerts_start_and_clear(staff, offline, monkeypatch, app_env):
    a = staff("owner")
    DU = namedtuple("DU", "total used free")
    monkeypatch.setattr(offline.shutil, "disk_usage", lambda p: DU(100, 90, 10))
    r = a.post("/api/admin/system/alerts/check").json()
    assert r["alerts"][0]["key"] == "disk"
    assert any(n["id"] == "alert-disk" for n in a.get("/api/admin/notifications").json()["items"])
    a.post("/api/admin/system/alerts/check")                                          # no duplicate email
    monkeypatch.setattr(offline.shutil, "disk_usage", lambda p: DU(100, 50, 50))
    assert a.post("/api/admin/system/alerts/check").json()["alerts"] == []
    from sqlalchemy import select

    from models import EmailLog

    async def logs(db):
        return [(e.template, e.subject) for e in (await db.execute(select(EmailLog))).scalars()]
    sent = run_db(app_env, logs)
    assert [t for t, _ in sent] == ["system_alert", "system_alert"]
    assert "Disk 90% full" in sent[0][1] and "RESOLVED" in sent[1][1]


def test_backups(staff, monkeypatch, tmp_path, clock):
    from admin import health
    from settings import get_settings
    monkeypatch.setattr(health, "BACKUP_DIR", tmp_path)
    a = staff("owner")
    assert a.get("/api/admin/backups").json()["configured"] is False
    assert a.post("/api/admin/backups/run").status_code == 503
    monkeypatch.setenv("AIWAZZ_BACKUP_PASSPHRASE", "test-passphrase")
    get_settings.cache_clear()
    # A tiny archive in the real format, encrypted like make_backup does
    work = tmp_path / "w"
    work.mkdir()
    (work / "aiwazz_voice.sql").write_text("CREATE TABLE users (id int);\nCREATE TABLE x (id int);\n-- Dump completed on 2026-11-24\n")
    (work / "MANIFEST.json").write_text("{}")
    subprocess.run(["tar", "-czf", str(tmp_path / "b.tgz"), "-C", str(work), "aiwazz_voice.sql", "MANIFEST.json"], check=True)
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-in", str(tmp_path / "b.tgz"),
                    "-out", str(tmp_path / "aiwazz-20261124-0230.tar.gz.enc"), "-pass", "env:P"], check=True, env={**os.environ, "P": "test-passphrase"})
    lst = a.get("/api/admin/backups").json()
    assert lst["configured"] and lst["items"][0]["name"] == "aiwazz-20261124-0230.tar.gz.enc"
    v = a.post("/api/admin/backups/verify").json()
    assert v["ok"] is True and v["tables"] == 2 and "MANIFEST.json" in v["files"]
    assert a.get("/api/admin/backups/latest/download").status_code == 403
    stepup(a, clock)
    r = a.get("/api/admin/backups/latest/download")
    assert r.status_code == 200 and r.content[:8] == b"Salted__"                     # encrypted, never plain SQL
    assert staff("admin").get("/api/admin/backups/latest/download").status_code == 403    # owner only (backups.download)


def test_request_id_header(client):
    r = client.get("/api/auth/me")
    assert len(r.headers["x-request-id"]) == 12

"""A8: metrics_daily aggregation, server-log visits (bots/assets/own IP excluded, no IPs stored), analytics
endpoint (totals, compare, funnel, popularity, Hinglish share, cohorts, privacy of top users for viewers)."""
from datetime import timedelta

from tests.conftest import run_db


def test_visits_from_access_log(tmp_path):
    from admin import metrics
    log = tmp_path / "access.log"
    log.write_text(
        '1.2.3.4 - - [24/Nov/2026:08:00:00 -0600] "GET / HTTP/2.0" 200 100 "-" "Mozilla/5.0 (iPhone)"\n'
        '1.2.3.4 - - [24/Nov/2026:08:00:05 -0600] "GET /pricing/ HTTP/2.0" 200 100 "-" "Mozilla/5.0 (iPhone)"\n'
        '1.2.3.4 - - [24/Nov/2026:08:00:05 -0600] "GET /_astro/a.css HTTP/2.0" 200 100 "-" "Mozilla/5.0 (iPhone)"\n'
        '5.6.7.8 - - [24/Nov/2026:09:00:00 -0600] "GET /learn/ HTTP/2.0" 200 100 "-" "Mozilla/5.0 (Windows)"\n'
        '9.9.9.9 - - [24/Nov/2026:09:00:00 -0600] "GET / HTTP/2.0" 200 100 "-" "Googlebot/2.1"\n'
        '104.237.6.214 - - [24/Nov/2026:09:00:00 -0600] "GET / HTTP/2.0" 200 100 "-" "Mozilla/5.0"\n'
        '5.6.7.8 - - [24/Nov/2026:09:01:00 -0600] "GET /missing HTTP/2.0" 404 100 "-" "Mozilla/5.0 (Windows)"\n'
        '5.6.7.8 - - [24/Nov/2026:13:00:00 -0600] "GET / HTTP/2.0" 200 100 "-" "Mozilla/5.0 (Windows)"\n')   # 00:30 IST next day
    from datetime import date
    v = metrics.visits_for({date(2026, 11, 24), date(2026, 11, 25)}, log)
    assert v[date(2026, 11, 24)] == (3, 2) and v[date(2026, 11, 25)] == (1, 1)
    assert metrics.log_covers(date(2026, 11, 24), log) and not metrics.log_covers(date(2026, 11, 23), log)


def test_compute_and_store_day(client, app_env, set_plan):
    client.post("/api/tts?wait=true", json={"text": "Namaste dosto.", "voice": "hf_beta", "transliterate": True})
    client.post("/api/tts?wait=true", json={"text": "Hello there friend.", "voice": "am_puck", "style": "calm-narrator"})
    from admin import metrics

    async def go(db):
        d = metrics.today_ist()
        vals = await metrics.compute_day(db, d, (10, 4))
        await metrics.store_day(db, d, vals)
        await metrics.store_day(db, d, vals)          # idempotent
        from sqlalchemy import func, select

        from models import MetricDaily
        n = (await db.execute(select(func.count()).select_from(MetricDaily))).scalar_one()
        return vals, n
    vals, n = run_db(app_env, go)
    assert vals["signups"] == 1 and vals["generations_done"] == 2 and vals["first_generation"] == 1
    assert vals["voice:hf_beta"] == 1 and vals["style:calm-narrator"] == 1 and vals["lang:h"] == 1 and vals["hinglish"] == 1
    assert vals["chars"] == len("Namaste dosto.") + len("Hello there friend.") and vals["visitors"] == 4
    assert n == len(vals) + 1                       # + the _computed marker


def test_nightly_backfill(client, app_env):
    from sqlalchemy import update

    from db import utcnow
    from models import User

    async def age(db):
        await db.execute(update(User).values(created_at=utcnow() - timedelta(days=5)))
    run_db(app_env, age)
    from admin import metrics
    out = run_db(app_env, lambda db: metrics.nightly(db))
    assert out.startswith("5 day")
    assert run_db(app_env, lambda db: metrics.nightly(db)).startswith("1 day")   # only yesterday again


def test_analytics_endpoint(staff, client):
    client.post("/api/tts?wait=true", json={"text": "Namaste dosto.", "voice": "hf_beta", "transliterate": True})
    a = staff("admin")
    from admin import metrics
    today = metrics.today_ist()
    r = a.get(f"/api/admin/analytics?start={(today - timedelta(days=6)).isoformat()}&end={today.isoformat()}")
    d = r.json()
    assert r.status_code == 200 and d["totals"]["signups"] == 2 and d["totals"]["generations_done"] == 1
    assert d["previous"]["signups"] == 0 and len(d["series"]["signups"]) == 7
    assert [f["step"] for f in d["funnel"]] == ["Visitors (aiwazz.in)", "Signups", "First voiceover", "First payment"]
    assert d["popularity"]["voices"][0]["id"] == "hf_beta" and d["hinglish_pct"] == 100.0
    assert d["cohorts"][-1]["size"] == 1 and d["cohorts"][-1]["retention"][0] == 100
    assert d["top_users"][0]["email"] == "me@example.com"
    v = staff("viewer").get(f"/api/admin/analytics?start={today.isoformat()}&end={today.isoformat()}").json()
    assert v["top_users"][0]["email"].startswith("user #")                                 # viewer: no emails
    assert a.get(f"/api/admin/analytics?start={today.isoformat()}&end={(today - timedelta(days=1)).isoformat()}").status_code == 422

#!/usr/bin/env python3
"""API watchdog (PM2 "aiwazz-watchdog", cron every 5 minutes, outside the API process).

Checks http://127.0.0.1:8100/api/health (3 tries), writes api/storage/watchdog.json (shown in admin → System health;
an "API was down" alert is raised from it) and, when the API is down twice in a row, emails support@ directly through
the local mail server (only if mail is enabled). PM2 itself restarts a crashed voice-api; this tells a human."""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api"
STATE = API / "storage" / "watchdog.json"


def check() -> tuple[bool, str]:
    last = ""
    for _ in range(3):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8100/api/health", timeout=10) as r:
                if r.status == 200:
                    return True, "healthy"
                last = f"HTTP {r.status}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)
    return False, last


def main() -> None:
    prev = {}
    try:
        prev = json.loads(STATE.read_text())
    except (OSError, ValueError):
        pass
    ok, detail = check()
    fails = 0 if ok else int(prev.get("fails", 0)) + 1
    state = {"checked_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z", "api_ok": ok, "detail": detail,
             "fails": fails, "last_down_at": prev.get("last_down_at") if ok else datetime.now(timezone.utc).isoformat()}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))
    if fails == 2:
        sys.path.insert(0, str(API))
        try:
            import asyncio

            import mailer
            from settings import get_settings
            s = get_settings()
            msg = mailer.build(s.support_email, "[AiWazz alert] API is down",
                               f"The API failed its health check twice in a row ({detail}).\nPM2 restarts it automatically; "
                               "check https://login.aiwazz.in/admin/health and `pm2 logs voice-api`.\n")
            asyncio.run(mailer.send(msg))
        except Exception as e:  # noqa: BLE001
            print(f"alert email failed: {e}")
    print(json.dumps(state))


if __name__ == "__main__":
    main()

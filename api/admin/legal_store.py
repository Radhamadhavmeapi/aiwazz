"""legal/legal.json is the single source of truth for company data and plans. The admin panel edits it through a
validated write: schema check → diff preview → atomic write → git commit (+ push in the background) → in-process
reload → landing rebuild + deploy (background job, logged in task_runs)."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .jobs import ROOT, run_cmd

PATH = ROOT / "legal" / "legal.json"
PLAN_IDS = ("free", "starter", "creator", "pro")
VISIBILITY = ("public", "hidden", "legacy")
REQUIRED_STR = ("product", "brand", "legalName", "gstin", "address", "supportEmail", "legalEmail", "privacyEmail",
                "jurisdiction", "effectiveDate", "lastUpdated", "currency", "sacCode")


def read() -> dict:
    return json.loads(PATH.read_text())


def validate(d: Any) -> list[str]:
    """Problems with a proposed legal.json (empty list = valid)."""
    import re
    errs: list[str] = []
    if not isinstance(d, dict):
        return ["Top level must be an object"]
    for k in REQUIRED_STR:
        if not isinstance(d.get(k), str) or not d[k].strip():
            errs.append(f"{k}: required text")
    if isinstance(d.get("gstin"), str) and not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", d["gstin"]):
        errs.append("gstin: not a valid GSTIN format")
    for k in ("supportEmail", "legalEmail", "privacyEmail"):
        if isinstance(d.get(k), str) and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", d[k]):
            errs.append(f"{k}: not an email address")
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    for k in ("effectiveDate", "lastUpdated"):
        if isinstance(d.get(k), str) and not re.fullmatch(rf"([1-9]|[12]\d|3[01]) ({months}) 20\d\d", d[k]):
            errs.append(f"{k}: write it like 24 November 2026")
    if not isinstance(d.get("gstRatePercent"), int) or not 0 <= d["gstRatePercent"] <= 28:
        errs.append("gstRatePercent: whole number 0-28")
    if not isinstance(d.get("yearlyDiscountPercent"), int) or not 0 <= d["yearlyDiscountPercent"] <= 90:
        errs.append("yearlyDiscountPercent: whole number 0-90")
    if not isinstance(d.get("audioRetentionDays"), int) or not 1 <= d["audioRetentionDays"] <= 365:
        errs.append("audioRetentionDays: 1-365")
    go = d.get("grievanceOfficer")
    if not isinstance(go, dict) or not str(go.get("name", "")).strip():
        errs.append("grievanceOfficer.name: required")
    plans = d.get("plans")
    if not isinstance(plans, list) or [p.get("id") if isinstance(p, dict) else None for p in plans] != list(PLAN_IDS):
        errs.append(f"plans: exactly {', '.join(PLAN_IDS)} in this order")
        return errs
    popular = 0
    for p in plans:
        pid = p["id"]
        if not isinstance(p.get("name"), str) or not p["name"].strip() or len(p["name"]) > 30:
            errs.append(f"plans.{pid}.name: 1-30 characters")
        if not isinstance(p.get("priceMonthly"), int) or p["priceMonthly"] < 0 or p["priceMonthly"] > 100000:
            errs.append(f"plans.{pid}.priceMonthly: whole rupees 0-100000")
        if pid == "free" and p.get("priceMonthly") != 0:
            errs.append("plans.free.priceMonthly must be 0")
        if pid != "free" and isinstance(p.get("priceMonthly"), int) and p["priceMonthly"] < 1:
            errs.append(f"plans.{pid}.priceMonthly: paid plans cost at least ₹1")
        if not isinstance(p.get("characters"), int) or not 100 <= p["characters"] <= 100_000_000:
            errs.append(f"plans.{pid}.characters: 100-100,000,000")
        f = p.get("features")
        if not isinstance(f, list) or not 1 <= len(f) <= 12 or not all(isinstance(x, str) and 0 < len(x) <= 120 for x in f):
            errs.append(f"plans.{pid}.features: 1-12 lines of up to 120 characters")
        if p.get("visibility", "public") not in VISIBILITY:
            errs.append(f"plans.{pid}.visibility: public, hidden or legacy")
        if pid == "free" and p.get("visibility", "public") != "public":
            errs.append("plans.free must stay public")
        if "sortOrder" in p and not isinstance(p["sortOrder"], int):
            errs.append(f"plans.{pid}.sortOrder: whole number")
        popular += bool(p.get("popular"))
    if popular > 1:
        errs.append("Only one plan can be \"most popular\"")
    return errs


def diff(before: Any, after: Any, path: str = "") -> list[dict]:
    """Flat list of changes {path, before, after} for the preview."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for k in sorted(set(before) | set(after), key=str):
            out += diff(before.get(k), after.get(k), f"{path}.{k}" if path else str(k))
        return out
    if isinstance(before, list) and isinstance(after, list) and all(isinstance(x, dict) and "id" in x for x in before + after):
        b, a = {x["id"]: x for x in before}, {x["id"]: x for x in after}
        out = []
        for k in list(b) + [k for k in a if k not in b]:
            out += diff(b.get(k), a.get(k), f"{path}[{k}]")
        return out
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def write_atomic(d: dict) -> None:
    text = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=PATH.parent, prefix=".legal-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, PATH)


def reload_in_process() -> None:
    """Update the module-level copies (in place, so every `from x import LEGAL` reference sees the change)."""
    import usage
    from billing import gst
    from settings import get_settings
    new = read()
    gst.LEGAL.clear()
    gst.LEGAL.update(new)
    usage.PLANS.clear()
    usage.PLANS.update(usage._plans())
    get_settings().terms_version = new.get("lastUpdated", "unknown")


async def commit(message: str, author: str) -> str:
    """git add + commit legal/legal.json in the repo clone (push runs separately, best effort)."""
    await run_cmd("git", "add", "legal/legal.json")
    await run_cmd("git", "-c", "user.name=AiWazz Admin", "-c", "user.email=admin-panel@aiwazz.in", "commit", "-m",
                  f"{message}\n\nChanged in the admin panel by {author}.", "--", "legal/legal.json")
    return (await run_cmd("git", "rev-parse", "--short", "HEAD")).strip()


async def push_and_rebuild_landing() -> str:
    """Background job: push the commit, rebuild + deploy aiwazz.in (tools/deploy-landing.sh)."""
    notes = []
    try:
        await run_cmd("git", "push", "-q", "origin", "main", timeout=120)
        notes.append("pushed")
    except RuntimeError as e:
        notes.append(f"push failed ({e}); push by hand")
    out = await run_cmd(str(ROOT / "tools" / "deploy-landing.sh"), timeout=1200,
                        env={"PATH": "/www/server/nodejs/v24.11.1/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"})
    notes.append(out.splitlines()[-1] if out else "landing deployed")
    return "; ".join(notes)

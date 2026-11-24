"""A6: system health (host, processes, DB, Redis, SSL, mail, storage, backups, alerts), PM2 restart (step-up),
log viewer (redacted), backups (run now, verify, download latest: step-up)."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from db import get_db

from .. import health, jobs, settings_store
from ..audit import audit
from ..deps import require_perm, require_stepup, staff_principal

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)


@router.get("/system")
async def system(request: Request, p: Principal = Depends(require_perm("system.read")), db: AsyncSession = Depends(get_db)):
    return await health.collect(request.app, db)


class RestartIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/system/processes/{name}/restart")
async def restart_process(name: str, body: RestartIn, request: Request, p: Principal = Depends(require_perm("system.write")),
                          _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    if name not in health.PROCESSES:
        raise HTTPException(404, "Only AiWazz processes can be restarted here")
    audit(db, request, p.user, "system.process.restart", target_type="process", target_id=name, label=name, reason=body.reason)
    await db.commit()

    async def later():
        await asyncio.sleep(1.5)      # answer first: restarting voice-api restarts this very process
        await health._run(health.PM2, "restart", name, timeout=60)
    asyncio.get_running_loop().create_task(later())
    return {"ok": True, "message": f"{name} restarts in a moment" + (" (this page reconnects by itself)" if name == "voice-api" else "")}


@router.get("/logs")
async def logs(level: str = Query("", max_length=10), q: str = Query("", max_length=200), request_id: str = Query("", max_length=32),
               since: str = Query("", max_length=32), limit: int = Query(300, ge=1, le=2000), access: bool = False,
               p: Principal = Depends(require_perm("logs.read"))):
    items = await asyncio.to_thread(health.read_logs, level, q, request_id, since, limit, access)
    return {"items": items}


@router.post("/system/alerts/check")
async def check_alerts(request: Request, p: Principal = Depends(require_perm("system.read")), db: AsyncSession = Depends(get_db)):
    note = await health.check_and_notify(request.app, db)
    return {"note": note, "alerts": await health.active_alerts(db)}


@router.get("/backups")
async def backups(p: Principal = Depends(require_perm("backups.read")), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from models import TaskRun
    from settings import get_settings
    runs = (await db.execute(select(TaskRun).where(TaskRun.task.in_(("backup", "backup-verify"))).order_by(TaskRun.id.desc()).limit(20))).scalars().all()
    return {"items": health.list_backups(), "dir": str(health.BACKUP_DIR), "retention_days": health.BACKUP_RETENTION_DAYS,
            "configured": bool(get_settings().backup_passphrase), "running": jobs.is_running("backup"),
            "runs": [{"task": r.task, "status": r.status, "started_at": r.started_at.isoformat() + "Z", "detail": r.detail} for r in runs]}


@router.post("/backups/run")
async def run_backup(request: Request, p: Principal = Depends(require_perm("system.write")), db: AsyncSession = Depends(get_db)):
    from settings import get_settings
    if not get_settings().backup_passphrase:
        raise HTTPException(503, "Backups aren't configured yet (manage.py gen-backup-key)")
    started = jobs.start(request.app.state.sessionmaker, "backup", health.make_backup)
    audit(db, request, p.user, "system.backup.run", target_type="backup")
    await db.commit()
    return {"started": started}


@router.post("/backups/verify")
async def verify_latest(request: Request, p: Principal = Depends(require_perm("system.write")), db: AsyncSession = Depends(get_db)):
    latest = health.list_backups()[:1]
    if not latest:
        raise HTTPException(404, "No backup yet")
    res = await health.verify_backup(health.BACKUP_DIR / latest[0]["name"])
    audit(db, request, p.user, "system.backup.verify", target_type="backup", label=latest[0]["name"], after=res | {"files": len(res.get("files", []))}, full=True)
    await db.commit()
    return {"name": latest[0]["name"], **res}


@router.get("/backups/latest/download")
async def download_latest(request: Request, p: Principal = Depends(require_perm("backups.download")),
                          _s: Principal = Depends(require_stepup), db: AsyncSession = Depends(get_db)):
    latest = health.list_backups()[:1]
    if not latest:
        raise HTTPException(404, "No backup yet")
    audit(db, request, p.user, "export.backup", target_type="backup", label=latest[0]["name"])
    await db.commit()
    return FileResponse(health.BACKUP_DIR / latest[0]["name"], media_type="application/octet-stream", filename=latest[0]["name"])


class MailCfgIn(BaseModel):
    dkim_selector: str = Field(pattern=r"^[a-z0-9_\-]{1,40}$")


@router.put("/settings/mail")
async def set_mail_cfg(body: MailCfgIn, request: Request, p: Principal = Depends(require_perm("settings.write")), db: AsyncSession = Depends(get_db)):
    before = await settings_store.get(db, "mail")
    after = {**before, **body.model_dump()}
    await settings_store.put(db, "mail", after, p.user.id)
    audit(db, request, p.user, "settings.mail", target_type="setting", target_id="mail", before=before, after=after)
    await db.commit()
    return after

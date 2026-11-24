"""Server-side lists for the admin panel: pagination, whitelisted sorting, CSV export (step-up + audit)."""
import csv
import io
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal

from .audit import audit

MAX_EXPORT = 50_000


class ListParams:
    def __init__(self, page: int = Query(1, ge=1, le=100_000), size: int = Query(25, ge=1, le=200),
                 sort: str = Query("", max_length=40), q: str = Query("", max_length=200),
                 format: str = Query("json", pattern="^(json|csv)$")):
        self.page, self.size, self.sort, self.q, self.format = page, size, sort, q.strip(), format


def iso(d: datetime | None) -> str | None:
    return d.isoformat() + "Z" if d else None


def apply_sort(stmt: Select, sort: str, allowed: dict[str, Any], default: Any) -> Select:
    if sort:
        desc = sort.startswith("-")
        col = allowed.get(sort.lstrip("-"))
        if col is None:
            raise HTTPException(422, f"Can't sort by {sort.lstrip('-')}")
        return stmt.order_by(col.desc() if desc else col.asc())
    return stmt.order_by(default)


async def respond(db: AsyncSession, request: Request, p: Principal, stmt: Select, lp: ListParams, *,
                  sorts: dict[str, Any], default_sort: Any, row: Callable[[Any], dict], name: str,
                  scalars: bool = True, csv_row: Callable[[Any], dict] | None = None) -> Any:
    """JSON page {items,total,page,size} or the full filtered list as CSV (needs step-up; audited)."""
    stmt = apply_sort(stmt, lp.sort, sorts, default_sort)
    if lp.format == "csv":
        from .deps import stepup_ok
        from . import rbac
        if not rbac.has(p.user.role, "export"):
            raise HTTPException(403, "Your role doesn't allow exports")
        if not stepup_ok(p):
            raise HTTPException(403, "Confirm it's you (password + 2FA code) to continue", headers={"X-Step-Up": "required"})
        res = await db.execute(stmt.limit(MAX_EXPORT))
        rows = res.scalars().all() if scalars else res.all()
        data = [(csv_row or row)(r) for r in rows]
        audit(db, request, p.user, "export.csv", target_type=name, label=f"{len(data)} rows",
              after={"filters": dict(request.query_params)}, full=True)
        await db.commit()
        return csv_response(data, f"aiwazz-{name}.csv")
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    res = await db.execute(stmt.offset((lp.page - 1) * lp.size).limit(lp.size))
    rows = res.scalars().all() if scalars else res.all()
    return {"items": [row(r) for r in rows], "total": total, "page": lp.page, "size": lp.size}


def _cell(v: Any) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    s = "" if v is None else str(v)
    # CSV/formula injection: a cell starting with = + - @ is treated as a formula by Excel.
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def csv_response(rows: Sequence[dict], filename: str) -> Response:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(v) for k, v in r.items()})
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

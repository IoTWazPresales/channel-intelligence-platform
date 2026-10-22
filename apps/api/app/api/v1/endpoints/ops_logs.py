"""Admin live log view (N-0089): the existing log files over Server-Sent Events, secrets masked on the server.

``GET /admin/logs/stream``  SSE: one ``backlog`` event, then ``lines`` events as the files grow, ``: ping`` comments
                            while quiet, and an ``end`` event when the stream reaches its maximum length (the page
                            reconnects). Filters here are the ones that change what is read: ``sources`` and ``job_id``.
``GET /admin/logs/errors``  The newest ERROR line and how many are newer than ``since``; the red dot polls this.

Admin only. Nothing is written, and the files are the ones the supervisor already keeps.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db
from app.core.log_masking import LogMasker
from app.core.security import Role, require_roles
from app.services import ops_logs

router = APIRouter()

POLL_SECONDS = 1.0
PING_SECONDS = 15.0
MAX_STREAM_SECONDS = 3600.0


def _sources(raw: str | None) -> list[str]:
    names = [p.strip().lower() for p in (raw or "").split(",") if p.strip()]
    chosen = [n for n in names if n in ops_logs.SOURCES]
    return chosen or list(ops_logs.DEFAULT_SOURCES)


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/logs/stream")
async def stream_logs(
    request: Request,
    sources: str | None = Query(default=None, description="Comma list of api, worker, web, supervisor; default all"),
    job_id: int | None = Query(default=None, ge=1, description="Only lines for this import job id"),
    level: str | None = Query(default=None, description="Least severe level to send (DEBUG..CRITICAL)"),
    backlog: int = Query(default=300, ge=0, le=1000),
    access: bool = Query(default=False, description="Include the API's per-request access lines"),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles(Role.ADMIN)),
):
    # The auth lookup left a transaction open on this session; a stream can run for an hour, so give the
    # connection back to the pool now (the session is not used again).
    await db.close()

    chosen = _sources(sources)
    stream = ops_logs.LogStream(chosen, job_id=job_id, min_level=level, include_access=access, masker=LogMasker())

    async def events():
        first = await run_in_threadpool(stream.backlog, backlog)
        yield _event(
            "backlog",
            {
                "lines": first,
                "sources": chosen,
                "job_id": job_id,
                "log_dir_found": ops_logs.log_dir().is_dir(),
            },
        )
        # backlog() read each file to its end; poll() continues from there.
        started = last_sent = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            now = time.monotonic()
            if now - started >= MAX_STREAM_SECONDS:
                yield _event("end", {"reason": "max-duration"})
                return
            fresh = await run_in_threadpool(stream.poll)
            if fresh:
                yield _event("lines", {"lines": fresh})
                last_sent = now
            elif now - last_sent >= PING_SECONDS:
                yield ": ping\n\n"
                last_sent = now
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/logs/errors")
async def newest_errors(
    since: str | None = Query(default=None, description="Local ISO time of the last error the page showed"),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles(Role.ADMIN)),
):
    await db.close()
    return await run_in_threadpool(ops_logs.latest_errors, since, masker=LogMasker())

"""Persist background-task snapshots for polling (nav activity feed, page banners)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import uuid4

from app.core.redis_sync import get_sync_redis

logger = logging.getLogger(__name__)

IDX_KEY = "cip:bg_tasks:timeline"
TASK_KEY_PREFIX = "cip:bg_task:"
TTL_SECONDS = 86400 * 7
PM_JOB_LINK_PREFIX = "cip:bg:pm_job:"


def _task_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


class BackgroundTaskStore:
    """Best-effort Redis persistence; all methods no-op safely when Redis is down."""

    @staticmethod
    def create_task(
        *,
        task_type: str,
        title: str,
        status: str = "queued",
        import_job_id: int | None = None,
        related_import_job_ids: list[int] | None = None,
        celery_task_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str | None:
        r = get_sync_redis()
        if r is None:
            return None
        task_id = str(uuid4())
        now = time.time()
        payload: dict[str, Any] = {
            "id": task_id,
            "type": task_type,
            "title": title,
            "status": status,
            "summary": "",
            "import_job_id": import_job_id,
            "related_import_job_ids": related_import_job_ids or [],
            "celery_task_id": celery_task_id,
            "lines_total": None,
            "lines_processed": None,
            "newly_resolved": None,
            "still_unresolved": None,
            "created_at": now,
            "updated_at": now,
            "dismissed": False,
            "error_message": None,
        }
        if extra is not None:
            payload.update(extra)
        try:
            r.set(_task_key(task_id), json.dumps(payload), ex=TTL_SECONDS)
            r.zadd(IDX_KEY, {task_id: now})
            r.expire(IDX_KEY, TTL_SECONDS)
        except Exception:
            logger.exception("background task create failed task_id=%s", task_id)
            return None
        return task_id

    @staticmethod
    def link_pm_import_job(job_id: int, task_id: str) -> None:
        r = get_sync_redis()
        if r is None:
            return
        try:
            r.set(f"{PM_JOB_LINK_PREFIX}{int(job_id)}", task_id, ex=TTL_SECONDS)
        except Exception:
            logger.exception("link_pm_import_job failed job_id=%s", job_id)

    @staticmethod
    def get_pm_linked_task_id(job_id: int) -> str | None:
        r = get_sync_redis()
        if r is None:
            return None
        try:
            tid = r.get(f"{PM_JOB_LINK_PREFIX}{int(job_id)}")
            return str(tid) if tid else None
        except Exception:
            return None

    @staticmethod
    def update_task(task_id: str, **fields: Any) -> None:
        r = get_sync_redis()
        if r is None:
            return
        try:
            raw = r.get(_task_key(task_id))
            if not raw:
                return
            data = json.loads(raw)
            for k, v in fields.items():
                data[k] = v
            data["updated_at"] = time.time()
            if data.get("type") == "shipment_product_reresolution":
                data["summary"] = BackgroundTaskStore.rebuild_summary_reresolution(data)
            elif data.get("type") == "product_master_commit":
                ph = data.get("commit_phase")
                if ph == "running":
                    data["summary"] = "Writing products to catalogue…"
                elif ph == "completed":
                    data["summary"] = "Product Master commit finished."
                elif ph == "failed":
                    data["summary"] = data.get("error_message") or "Product Master commit failed."
                else:
                    data["summary"] = "Queued for background worker…"
            r.set(_task_key(task_id), json.dumps(data), ex=TTL_SECONDS)
            r.zadd(IDX_KEY, {task_id: data["updated_at"]})
        except Exception:
            logger.exception("background task update failed task_id=%s", task_id)

    @staticmethod
    def get_task(task_id: str) -> dict[str, Any] | None:
        r = get_sync_redis()
        if r is None:
            return None
        try:
            raw = r.get(_task_key(task_id))
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            logger.exception("background task get failed task_id=%s", task_id)
            return None

    @staticmethod
    def dismiss_task(task_id: str) -> bool:
        r = get_sync_redis()
        if r is None:
            return False
        try:
            raw = r.get(_task_key(task_id))
            if not raw:
                return False
            data = json.loads(raw)
            data["dismissed"] = True
            data["updated_at"] = time.time()
            r.set(_task_key(task_id), json.dumps(data), ex=TTL_SECONDS)
            return True
        except Exception:
            logger.exception("background task dismiss failed task_id=%s", task_id)
            return False

    @staticmethod
    def list_tasks(*, limit: int = 80) -> list[dict[str, Any]]:
        r = get_sync_redis()
        if r is None:
            return []
        try:
            ids = r.zrevrange(IDX_KEY, 0, max(0, limit - 1))
            out: list[dict[str, Any]] = []
            for tid in ids:
                raw = r.get(_task_key(tid))
                if not raw:
                    r.zrem(IDX_KEY, tid)
                    continue
                row = json.loads(raw)
                if row.get("dismissed"):
                    continue
                out.append(row)
            return out
        except Exception:
            logger.exception("background task list failed")
            return []

    @staticmethod
    def rebuild_summary_reresolution(data: dict[str, Any]) -> str:
        lt = data.get("lines_total")
        lp = data.get("lines_processed")
        nr = data.get("newly_resolved")
        su = data.get("still_unresolved")
        if isinstance(lt, int) and isinstance(lp, int):
            base = f"{lp:,} / {lt:,} lines"
            if isinstance(nr, int):
                base += f", {nr:,} newly resolved"
            if isinstance(su, int):
                base += f", {su:,} still unresolved"
            return base
        return str(data.get("summary") or "")

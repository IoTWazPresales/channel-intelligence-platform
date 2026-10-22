"""Worker liveness the stale-job reaper can trust, without Celery's control plane (N-0089).

Why not ``inspect``: Celery answers control messages (``inspect().active()``) from the worker's main thread. A
``--pool=solo`` worker (the Windows default here) runs each task on that same thread, so while a task runs, including
the reaper's own task, ``inspect`` gets no answer and times out. The reaper therefore always saw "no workers"
(``'inspected': False``) and never reaped anything. Measured on a throwaway worker: solo answers only when idle; a
thread pool answers always.

What this does instead, for any pool:

* the worker runs a daemon thread that, every ``HEARTBEAT_EVERY_S``, writes ``cip:worker:heartbeat:<node>`` to the
  broker's Redis (expires after ``HEARTBEAT_TTL_S``) listing the task ids the worker is running (``active``) or holds
  (``reserved``), read from the same in-process state ``inspect`` reads (``celery.worker.state``). A daemon thread keeps
  running while the main thread is busy in a task; a dead worker stops writing and its key expires;
* ``live_task_ids`` reads every heartbeat plus the task ids still waiting in the broker queues (a job is set
  ``running`` when it is dispatched, so a task queued behind a long one is alive, not lost).

``None`` means "cannot tell" (no heartbeat, or Redis unreadable): the reaper then does nothing.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from celery.signals import task_postrun, task_prerun, task_received, worker_ready, worker_shutting_down

from app.core.config import get_settings
from app.worker.celery_queues import CELERY_QUEUE_BATCH, CELERY_QUEUE_DEFAULT, CELERY_QUEUE_INTERACTIVE

logger = logging.getLogger("app.worker.liveness")

HEARTBEAT_PREFIX = "cip:worker:heartbeat:"
HEARTBEAT_EVERY_S = 15.0
HEARTBEAT_TTL_S = 90
QUEUES = (CELERY_QUEUE_INTERACTIVE, CELERY_QUEUE_BATCH, CELERY_QUEUE_DEFAULT)
_PRIORITY_SEP = "\x06\x16"  # kombu's separator for priority variants of a queue's Redis list


def redis_client(url: str | None = None):
    import redis

    return redis.Redis.from_url(
        url or get_settings().celery_broker_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def _request_ids(requests: Iterable[Any]) -> list[str]:
    for _ in range(3):
        try:  # the main thread adds and removes while this thread reads
            return sorted({str(r.id) for r in list(requests) if getattr(r, "id", None)})
        except RuntimeError:
            continue
    return []


def local_task_ids() -> tuple[list[str], list[str]]:
    """(active, reserved) task ids of this worker process, as ``inspect`` would report them."""
    from celery.worker import state

    return _request_ids(state.active_requests), _request_ids(state.reserved_requests)


# Task ids this process has just been given or has just finished, tracked from signals so the heartbeat is current at
# every state change (celery.worker.state is updated slightly before or after the signals, so it alone can lag).
_TRACKED_GRACE_S = 60.0  # a tracked id the worker's own state no longer lists is dropped after this long
_tracked_lock = threading.Lock()
_tracked_active: dict[str, float] = {}
_tracked_reserved: dict[str, float] = {}


def _track(task_id: str | None, *, active: bool | None = None, reserved: bool | None = None) -> None:
    if not task_id:
        return
    tid = str(task_id)
    now = time.monotonic()
    with _tracked_lock:
        for flag, bucket in ((active, _tracked_active), (reserved, _tracked_reserved)):
            if flag is True:
                bucket[tid] = now
            elif flag is False:
                bucket.pop(tid, None)


def _tracked_ids(bucket: dict[str, float], in_state: set[str]) -> set[str]:
    """Tracked ids still worth reporting: listed by the worker's state, or tracked within the grace period.
    (A task that was received and then revoked or expired never reaches ``task_postrun``.)"""
    now = time.monotonic()
    for tid in [t for t, at in bucket.items() if t not in in_state and now - at > _TRACKED_GRACE_S]:
        del bucket[tid]
    return set(bucket)


def publish_heartbeat(client, node: str) -> dict[str, Any]:
    state_active, state_reserved = local_task_ids()
    in_state = set(state_active) | set(state_reserved)
    with _tracked_lock:
        active = sorted(set(state_active) | _tracked_ids(_tracked_active, in_state))
        reserved = sorted(set(state_reserved) | _tracked_ids(_tracked_reserved, in_state))
    payload = {
        "node": node,
        "pid": os.getpid(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "active": active,
        "reserved": reserved,
    }
    client.set(HEARTBEAT_PREFIX + node, json.dumps(payload), ex=HEARTBEAT_TTL_S)
    return payload


class WorkerHeartbeat(threading.Thread):
    def __init__(self, node: str, redis_url: str | None = None, every_s: float = HEARTBEAT_EVERY_S) -> None:
        super().__init__(name="cip-worker-heartbeat", daemon=True)
        self.node = node
        self._url = redis_url
        self._every = every_s
        self._stop_event = threading.Event()
        self._failing = False
        self._client = None

    def run(self) -> None:
        client = None
        while True:
            try:
                client = client or redis_client(self._url)
                publish_heartbeat(client, self.node)
                if self._failing:
                    logger.info("worker heartbeat to Redis is back (node %s)", self.node)
                    self._failing = False
            except Exception as exc:  # never let the thread die: the next beat may work
                client = None
                if not self._failing:
                    logger.warning("worker heartbeat could not be written (node %s): %s", self.node, exc)
                    self._failing = True
            if self._stop_event.wait(self._every):
                break
        try:
            (client or redis_client(self._url)).delete(HEARTBEAT_PREFIX + self.node)
        except Exception:
            pass

    def publish_now(self) -> None:
        """Write the heartbeat now (a task was received, started or finished); the periodic beat is the backstop."""
        try:
            publish_heartbeat(self._publish_client(), self.node)
        except Exception:
            self._client = None

    def _publish_client(self):
        if getattr(self, "_client", None) is None:
            self._client = redis_client(self._url)
        return self._client

    def stop(self) -> None:
        self._stop_event.set()


_current: WorkerHeartbeat | None = None


def _publish_now() -> None:
    hb = _current
    if hb is not None and hb.is_alive():
        hb.publish_now()


@task_received.connect
def _on_task_received(request=None, **_kwargs) -> None:
    _track(getattr(request, "id", None), reserved=True)
    _publish_now()


@task_prerun.connect
def _on_task_prerun(task_id=None, **_kwargs) -> None:
    _track(task_id, active=True, reserved=True)
    _publish_now()


@task_postrun.connect
def _on_task_postrun(task_id=None, **_kwargs) -> None:
    _track(task_id, active=False, reserved=False)
    _publish_now()


def start_worker_heartbeat(node: str, redis_url: str | None = None, every_s: float = HEARTBEAT_EVERY_S) -> WorkerHeartbeat:
    global _current
    if _current is not None and _current.is_alive():
        return _current
    _current = WorkerHeartbeat(node, redis_url, every_s)
    _current.start()
    logger.info("worker heartbeat started (node %s, every %.0fs, expires after %ss)", node, every_s, HEARTBEAT_TTL_S)
    return _current


def stop_worker_heartbeat() -> None:
    global _current
    if _current is not None:
        _current.stop()
        _current.join(timeout=5)
        _current = None


@worker_ready.connect
def _start_heartbeat_when_worker_is_ready(sender=None, **_kwargs) -> None:
    node = getattr(sender, "hostname", None) or f"celery@{socket.gethostname()}"
    start_worker_heartbeat(str(node))


@worker_shutting_down.connect
def _stop_heartbeat_on_shutdown(**_kwargs) -> None:
    stop_worker_heartbeat()


def read_heartbeats(client) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in client.scan_iter(match=HEARTBEAT_PREFIX + "*"):
        raw = client.get(key)
        if not raw:
            continue
        try:
            beat = json.loads(raw)
        except ValueError:
            continue
        if isinstance(beat, dict):
            out.append(beat)
    return out


def _task_id_from_message(raw: str) -> str | None:
    try:
        msg = json.loads(raw)
    except ValueError:
        return None
    headers = msg.get("headers") if isinstance(msg, dict) else None
    tid = (headers or {}).get("id") or ((msg.get("properties") or {}).get("correlation_id") if isinstance(msg, dict) else None)
    return str(tid) if tid else None


def queued_task_ids(client, queues: Iterable[str] = QUEUES) -> set[str]:
    """Ids of tasks still waiting in the broker's queues (not yet taken by a worker)."""
    ids: set[str] = set()
    for q in queues:
        keys = [q, *client.scan_iter(match=f"{q}{_PRIORITY_SEP}*")]
        for key in keys:
            for raw in client.lrange(key, 0, -1):
                tid = _task_id_from_message(raw)
                if tid:
                    ids.add(tid)
    return ids


def live_task_ids(client=None) -> set[str] | None:
    """Task ids a live worker is running or holds, plus tasks waiting in the queues; ``None`` when unknown."""
    try:
        client = client or redis_client()
        beats = read_heartbeats(client)
        if not beats:
            logger.warning(
                "no worker heartbeat in Redis (%s*): cannot tell which tasks are alive; "
                "is the worker running code with app.worker.liveness?",
                HEARTBEAT_PREFIX,
            )
            return None
        ids: set[str] = set()
        for beat in beats:
            ids.update(str(t) for t in beat.get("active") or [])
            ids.update(str(t) for t in beat.get("reserved") or [])
        ids |= queued_task_ids(client)
        return ids
    except Exception as exc:
        logger.warning("worker liveness could not be read from Redis: %s", exc)
        return None

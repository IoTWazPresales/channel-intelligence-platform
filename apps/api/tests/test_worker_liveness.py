"""N-0089: the worker heartbeat the stale-job reaper reads instead of ``celery inspect``.

Context: a ``--pool=solo`` worker cannot answer ``inspect`` while it runs a task (including the reaper's own task),
so the reaper always saw "no workers" and reaped nothing. These tests use an in-memory stand-in for Redis.
"""

from __future__ import annotations

import fnmatch
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.imports.running_import_job_reaper import reap_stale_running_import_jobs_sync
from app.worker import liveness


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.expiry: dict[str, int] = {}

    def set(self, key, value, ex=None):
        self.kv[key] = value
        if ex is not None:
            self.expiry[key] = ex

    def get(self, key):
        return self.kv.get(key)

    def delete(self, key):
        self.kv.pop(key, None)

    def scan_iter(self, match="*"):
        yield from [k for k in [*self.kv, *self.lists] if fnmatch.fnmatchcase(k, match)]

    def lrange(self, key, start, end):
        return list(self.lists.get(key, []))


def _kombu_message(task_id: str, task: str = "imports.cst_apply") -> str:
    return json.dumps({"body": "e30=", "headers": {"lang": "py", "task": task, "id": task_id}, "properties": {"correlation_id": task_id}})


@pytest.fixture(autouse=True)
def _clean_tracking():
    liveness._tracked_active.clear()
    liveness._tracked_reserved.clear()
    yield
    liveness._tracked_active.clear()
    liveness._tracked_reserved.clear()


def _beat(r: FakeRedis, node: str, active=(), reserved=()) -> None:
    r.set(liveness.HEARTBEAT_PREFIX + node, json.dumps({"node": node, "pid": 1, "ts": "x", "active": list(active), "reserved": list(reserved)}))


def test_heartbeat_lists_what_the_worker_runs_and_holds_and_expires() -> None:
    r = FakeRedis()
    with patch.object(liveness, "local_task_ids", return_value=(["run-1"], ["run-1", "held-2"])):
        payload = liveness.publish_heartbeat(r, "celery@host")
    assert payload["active"] == ["run-1"] and payload["reserved"] == ["held-2", "run-1"]
    key = liveness.HEARTBEAT_PREFIX + "celery@host"
    assert json.loads(r.kv[key])["pid"] and r.expiry[key] == liveness.HEARTBEAT_TTL_S


def test_signals_keep_the_heartbeat_current_between_beats() -> None:
    liveness._track("t-1", reserved=True)
    liveness._track("t-1", active=True, reserved=True)
    with patch.object(liveness, "local_task_ids", return_value=([], [])):  # state not updated yet
        p = liveness.publish_heartbeat(FakeRedis(), "n")
    assert p["active"] == ["t-1"]
    liveness._track("t-1", active=False, reserved=False)
    with patch.object(liveness, "local_task_ids", return_value=([], [])):
        p = liveness.publish_heartbeat(FakeRedis(), "n")
    assert p["active"] == [] and p["reserved"] == []


def test_a_received_task_that_never_runs_stops_being_reported_after_the_grace_period() -> None:
    liveness._track("revoked-1", reserved=True)
    with patch.object(liveness, "local_task_ids", return_value=([], [])):
        assert liveness.publish_heartbeat(FakeRedis(), "n")["reserved"] == ["revoked-1"]
        liveness._tracked_reserved["revoked-1"] = time.monotonic() - liveness._TRACKED_GRACE_S - 1
        assert liveness.publish_heartbeat(FakeRedis(), "n")["reserved"] == []


def test_live_ids_are_running_plus_held_plus_still_queued() -> None:
    r = FakeRedis()
    _beat(r, "celery@host", active=["a"], reserved=["a", "b"])
    r.lists["batch"] = [_kombu_message("q1"), _kombu_message("q2")]
    r.lists["interactive"] = [_kombu_message("q3", "imports.cst_bulk_ignore")]
    r.lists["batch\x06\x163"] = [_kombu_message("q4")]  # a priority variant of the queue
    assert liveness.live_task_ids(r) == {"a", "b", "q1", "q2", "q3", "q4"}


def test_no_heartbeat_means_cannot_tell_not_nothing_is_alive() -> None:
    r = FakeRedis()
    r.lists["batch"] = [_kombu_message("q1")]
    assert liveness.live_task_ids(r) is None


def test_unreadable_redis_means_cannot_tell() -> None:
    broken = MagicMock()
    broken.scan_iter.side_effect = ConnectionError("redis down")
    assert liveness.live_task_ids(broken) is None


def test_two_workers_both_count() -> None:
    r = FakeRedis()
    _beat(r, "celery@one", active=["x"])
    _beat(r, "celery@two", active=["y"])
    assert liveness.live_task_ids(r) == {"x", "y"}


def test_a_garbled_queue_entry_is_skipped() -> None:
    r = FakeRedis()
    _beat(r, "n")
    r.lists["batch"] = ["not json", _kombu_message("ok")]
    assert liveness.live_task_ids(r) == {"ok"}


def test_heartbeat_thread_writes_then_removes_its_key_on_stop() -> None:
    r = FakeRedis()
    with patch.object(liveness, "redis_client", return_value=r), patch.object(liveness, "local_task_ids", return_value=([], [])):
        hb = liveness.WorkerHeartbeat("celery@thread-test", every_s=0.05)
        hb.start()
        deadline = time.time() + 5
        while liveness.HEARTBEAT_PREFIX + "celery@thread-test" not in r.kv and time.time() < deadline:
            time.sleep(0.02)
        assert liveness.HEARTBEAT_PREFIX + "celery@thread-test" in r.kv
        hb.stop()
        hb.join(timeout=5)
    assert liveness.HEARTBEAT_PREFIX + "celery@thread-test" not in r.kv


# ------------------------------------------------------------------------------------------------ the reaper

def _job(job_id: int, task_id: str, *, queued_minutes_ago: int = 30) -> MagicMock:
    now = datetime.now(timezone.utc)
    job = MagicMock()
    job.id = job_id
    job.staged_metadata = {
        "celery_task_id": task_id,
        "pipeline_queued_at": (now - timedelta(minutes=queued_minutes_ago)).isoformat(),
    }
    return job


def _reap(live: set[str] | None, jobs: list[MagicMock]) -> dict:
    session = MagicMock()
    session.scalars.return_value.all.return_value = jobs
    with (
        patch("app.services.imports.running_import_job_reaper.live_task_ids", return_value=live),
        patch("app.services.imports.running_import_job_reaper.SessionLocal") as sl,
    ):
        sl.return_value.__enter__.return_value = session
        return reap_stale_running_import_jobs_sync()


def test_reaper_reaps_a_job_whose_task_is_not_running_held_or_queued() -> None:
    dead, running, queued, held = _job(1, "dead"), _job(2, "run"), _job(3, "queued"), _job(4, "held")
    out = _reap({"run", "queued", "held"}, [dead, running, queued, held])
    assert out["inspected"] is True and out["job_ids"] == [1]
    assert dead.status == "failed"
    assert not isinstance(running.status, str) or running.status != "failed"


def test_reaper_never_reaps_a_job_queued_behind_a_long_task() -> None:
    """A job is set running when it is dispatched, so a queued task older than the grace period is alive."""
    job = _job(7, "waiting-in-the-queue", queued_minutes_ago=45)
    out = _reap({"some-other-long-task", "waiting-in-the-queue"}, [job])
    assert out["marked_failed"] == 0


def test_reaper_does_nothing_when_liveness_cannot_be_read() -> None:
    out = _reap(None, [_job(1, "dead")])
    assert out == {"inspected": False, "scanned": 0, "marked_failed": 0, "job_ids": []}

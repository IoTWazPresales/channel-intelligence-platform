"""BACKLOG-245: deploy readiness reads the worker heartbeat (works while a solo worker is busy)."""

from datetime import datetime, timedelta, timezone

from app.worker import liveness_check as lc

NOW = datetime(2026, 11, 24, 1, 0, 0, tzinfo=timezone.utc)


def _beat(seconds_ago: float, pid: int = 42, node: str = "celery@pc") -> dict:
    return {"node": node, "pid": pid, "ts": (NOW - timedelta(seconds=seconds_ago)).isoformat(), "active": ["t1"]}


class _Redis:
    def __init__(self, beats):
        import json

        self.data = {f"cip:worker:heartbeat:{i}": json.dumps(b) for i, b in enumerate(beats)}

    def scan_iter(self, match=None):
        return iter(self.data)

    def get(self, key):
        return self.data.get(key)


def test_a_busy_worker_with_a_fresh_heartbeat_is_ready():
    out = lc.check(NOW - timedelta(seconds=60), 45, client=_Redis([_beat(10)]), now=NOW)
    assert out["ok"] is True and out["beats"][0]["pid"] == 42 and out["beats"][0]["age_s"] == 10.0


def test_a_heartbeat_from_before_the_restart_or_too_old_does_not_count():
    since = NOW - timedelta(seconds=20)
    assert lc.check(since, 45, client=_Redis([_beat(30)]), now=NOW)["reason"] == "no_fresh_heartbeat"
    assert lc.check(None, 45, client=_Redis([_beat(60)]), now=NOW)["ok"] is False
    assert lc.check(None, 45, client=_Redis([]), now=NOW)["reason"] == "no_heartbeat"


def test_unreadable_redis_is_not_ready():
    class Broken:
        def scan_iter(self, match=None):
            raise ConnectionError("down")

    out = lc.check(None, 45, client=Broken(), now=NOW)
    assert out["ok"] is False and out["reason"].startswith("redis_unreadable")


def test_newest_beat_first_and_bad_rows_skipped():
    beats = [_beat(20, pid=1), _beat(5, pid=2), {"node": "x", "ts": "nope", "pid": 3}, {"node": "y", "ts": NOW.isoformat()}]
    fresh = lc.fresh_beats(beats, since=None, now=NOW)
    assert [b["pid"] for b in fresh] == [2, 1]
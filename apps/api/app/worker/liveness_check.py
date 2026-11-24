"""Deploy readiness from the worker heartbeat, not Celery's control plane (BACKLOG-245).

``celery inspect ping`` is answered on the worker's main thread. A ``--pool=solo`` worker that is busy in a
task (for example a listing-poll batch) cannot answer, so the Nov 22 deploy failed while the worker was healthy.
The heartbeat in ``app.worker.liveness`` is written by a daemon thread every 15 s whatever the main thread is
doing, so it is the readiness signal; ping stays a recorded diagnostic.

``python -m app.worker.liveness_check --since <ISO time> [--max-age 45]`` prints one JSON line:
``{"ok": bool, "reason": str | null, "beats": [{"node", "pid", "ts", "age_s"}]}`` and exits 0 when at least
one heartbeat was written at or after ``--since`` and is at most ``--max-age`` seconds old. The caller checks
that the reported pid is a running process (the deploy script does this on Windows).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from app.worker.liveness import HEARTBEAT_EVERY_S, read_heartbeats, redis_client

DEFAULT_MAX_AGE_S = 3 * HEARTBEAT_EVERY_S


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def fresh_beats(
    beats: list[dict[str, Any]],
    *,
    since: datetime | None,
    now: datetime,
    max_age_s: float = DEFAULT_MAX_AGE_S,
) -> list[dict[str, Any]]:
    """Heartbeats written after ``since`` and no older than ``max_age_s``, newest first."""
    out: list[dict[str, Any]] = []
    for beat in beats:
        ts = _parse_ts(beat.get("ts"))
        if ts is None or beat.get("pid") is None:
            continue
        age = (now - ts).total_seconds()
        if age > max_age_s or (since is not None and ts < since):
            continue
        out.append({"node": beat.get("node"), "pid": int(beat["pid"]), "ts": ts.isoformat(), "age_s": round(age, 1)})
    return sorted(out, key=lambda b: b["age_s"])


def check(since: datetime | None, max_age_s: float, client=None, now: datetime | None = None) -> dict[str, Any]:
    try:
        beats = read_heartbeats(client or redis_client())
    except Exception as exc:  # Redis unreadable: cannot tell, which is not ready
        return {"ok": False, "reason": f"redis_unreadable: {exc}", "beats": []}
    fresh = fresh_beats(beats, since=since, now=now or datetime.now(timezone.utc), max_age_s=max_age_s)
    if fresh:
        return {"ok": True, "reason": None, "beats": fresh}
    return {"ok": False, "reason": "no_fresh_heartbeat" if beats else "no_heartbeat", "beats": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.worker.liveness_check")
    parser.add_argument("--since", help="ISO time with offset (naive means UTC); only later heartbeats count")
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_S)
    args = parser.parse_args(argv)
    since = _parse_ts(args.since) if args.since else None
    if args.since and since is None:
        print(json.dumps({"ok": False, "reason": "bad_since", "beats": []}))
        return 2
    result = check(since, args.max_age)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
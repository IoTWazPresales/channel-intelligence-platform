"""Operations and data health for GET /ops/overview (Wave 3 Phase C, N-0089 scope).

Three parts, each with an explicit state, so a missing source reads as "unknown", never as ok:

- services: the always-on supervisor's ``status.json`` (scripts/cip-supervisor.ps1). A component is
  flapping when it launched more than ``FLAP_LIMIT`` times in 30 minutes (the supervisor's own
  limit);
  the whole file is stale when its heartbeat is older than ``HEARTBEAT_STALE_SECONDS``.
- backups: ``last_backup.json`` / ``last_restore.json`` written by
  scripts/ops/nightly_backup_cip.ps1.
  A backup older than ``BACKUP_MAX_AGE_HOURS`` or a restore test older than ``RESTORE_MAX_AGE_DAYS``
  is stale; a recorded failure is failed.
- reports: expected customer sell-through reports against the Monday-due rule (the
  ``customer_cst_report_slot`` tracker: due Monday, late from Tuesday, then missing), plus the newest
  received report, for the caller's tenant. ``ok`` needs receipt evidence; ``pending`` (due) and
  ``untracked`` (no slot / no recent receipt) are reported separately.

The pure functions take parsed JSON and ``now`` so they are tested without files or a database.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FLAP_LIMIT = 5
HEARTBEAT_STALE_SECONDS = 180
BACKUP_MAX_AGE_HOURS = 26
RESTORE_MAX_AGE_DAYS = 8
REPORT_RECEIPT_WINDOW_DAYS = 8  # weekly cadence plus the Tuesday-late grace
SUPERVISED = ("api", "worker", "web", "redis", "tunnel", "wsl")


def state_root(configured: str | None = None) -> Path | None:
    """%LOCALAPPDATA%\\CIP unless configured (CIP_OPS_STATE_DIR). None when neither is known."""
    if configured:
        return Path(configured)
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "CIP" if local else None


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _when(value: Any) -> datetime | None:
    """The supervisor and backup scripts write local 's' timestamps with no zone: local time."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(UTC)


def services_health(status: dict[str, Any] | None, *, now: datetime) -> dict[str, Any]:
    if not status:
        return {"state": "unknown", "detail": "No supervisor status file found.", "components": []}
    sup = status.get("supervisor") or {}
    beat = _when(sup.get("heartbeat"))
    age = None if beat is None else int((now - beat).total_seconds())
    stale = age is None or age > HEARTBEAT_STALE_SECONDS
    comps = status.get("components") or {}
    rows = []
    for name in SUPERVISED:
        c = comps.get(name)
        if not isinstance(c, dict):
            continue
        launches_30m = int(c.get("launches_30m") or 0)
        rows.append(
            {
                "name": name,
                "state": c.get("state"),
                "launches": c.get("launches"),
                "launches_30m": launches_30m,
                "flapping": launches_30m > FLAP_LIMIT,
                "last_healthy": c.get("last_healthy"),
                "detail": c.get("detail"),
            }
        )
    flapping = [r["name"] for r in rows if r["flapping"]]
    unhealthy = [r["name"] for r in rows if r["state"] not in ("healthy", None)]
    if stale:
        state, detail = (
            "stale",
            f"Supervisor heartbeat is {age if age is not None else 'unknown'} s old.",
        )
    elif flapping:
        state, detail = "flapping", "Restarting repeatedly: " + ", ".join(flapping) + "."
    elif unhealthy:
        state, detail = "degraded", "Not healthy: " + ", ".join(unhealthy) + "."
    else:
        state, detail = "ok", "All supervised parts healthy."
    return {
        "state": state,
        "detail": detail,
        "heartbeat_age_seconds": age,
        "flap_limit_30m": FLAP_LIMIT,
        "components": rows,
    }


def backups_health(
    last_backup: dict[str, Any] | None, last_restore: dict[str, Any] | None, *, now: datetime
) -> dict[str, Any]:
    out: dict[str, Any] = {"backup": None, "restore": None}
    if not last_backup:
        out["backup"] = {"state": "unknown", "detail": "No nightly backup has been recorded."}
    else:
        finished = _when(last_backup.get("finished"))
        age_h = None if finished is None else round((now - finished).total_seconds() / 3600, 1)
        if last_backup.get("result") != "ok":
            state, detail = "failed", str(last_backup.get("error") or "The last backup failed.")
        elif age_h is None or age_h > BACKUP_MAX_AGE_HOURS:
            state, detail = "stale", f"The last good backup is {age_h} hours old."
        else:
            state, detail = "ok", f"Verified backup {age_h} hours ago."
        out["backup"] = {
            "state": state,
            "detail": detail,
            "finished": last_backup.get("finished"),
            "age_hours": age_h,
            "bytes": last_backup.get("bytes"),
            "verified": bool(last_backup.get("verified")),
            "pruned": len(last_backup.get("pruned") or []),
        }
    if not last_restore:
        out["restore"] = {
            "state": "unknown",
            "detail": "No disposable restore test has been recorded.",
        }
    else:
        finished = _when(last_restore.get("finished"))
        age_d = None if finished is None else round((now - finished).total_seconds() / 86400, 1)
        if last_restore.get("result") != "ok":
            state, detail = (
                "failed",
                str(last_restore.get("detail") or "The last restore test failed."),
            )
        elif age_d is None or age_d > RESTORE_MAX_AGE_DAYS:
            state, detail = "stale", f"The last restore test is {age_d} days old."
        else:
            state, detail = "ok", f"Restore test passed {age_d} days ago."
        out["restore"] = {
            "state": state,
            "detail": detail,
            "finished": last_restore.get("finished"),
            "age_days": age_d,
        }
    states = [out["backup"]["state"], out["restore"]["state"]]
    out["state"] = next((s for s in ("failed", "stale", "unknown") if s in states), "ok")
    return out


def reports_health(
    *,
    late: int,
    missing: int,
    newest_received: datetime | None,
    expected_customers: int,
    now: datetime,
    due: int = 0,
    untracked_customers: int = 0,
) -> dict[str, Any]:
    """Monday-due rule: a slot is due on Monday, late on Tuesday and missing after that
    (imports/cst_d1.py).

    "ok" is only said with receipt evidence: a received report inside ``REPORT_RECEIPT_WINDOW_DAYS``
    and nothing outstanding. Absence of late/missing slots is not evidence, because the tracker may
    not have created or advanced any slot (``untracked``) and a ``due`` slot is simply still pending.
    Order, worst first: missing, late, untracked, pending, ok.
    """
    received = newest_received
    if received is not None and received.tzinfo is None:
        received = received.replace(tzinfo=UTC)
    age = None if received is None else now - received
    days = None if age is None else round(age.total_seconds() / 86400, 1)
    # Classify using the exact interval, never the rounded display age. Future receipts are not proof.
    has_evidence = age is not None and timedelta(0) <= age <= timedelta(days=REPORT_RECEIPT_WINDOW_DAYS)
    late, missing, due = int(late), int(missing), int(due)
    untracked_customers = int(untracked_customers)
    if expected_customers == 0:
        state, detail = "unknown", "No customer is set to send weekly reports."
    elif missing:
        state, detail = "missing", f"{late} late and {missing} missing expected reports."
    elif late:
        state, detail = "late", f"{late} expected reports are late."
    elif untracked_customers:
        state, detail = (
            "untracked",
            f"{untracked_customers} customers expected to report have no tracking slot "
            "with valid receipt evidence or a pending status for the current due week, "
            "so their reports cannot be confirmed.",
        )
    elif due:
        state, detail = "pending", f"{due} expected reports are due and have not arrived yet."
    elif not has_evidence:
        state = "untracked"
        detail = (
            "No report receipt has been recorded."
            if received is None
            else "The newest receipt is dated in the future and cannot confirm arrival."
            if age < timedelta(0)
            else f"The newest report arrived {days} days ago, outside the "
            f"{REPORT_RECEIPT_WINDOW_DAYS} day window, and no slot is outstanding."
        )
    else:
        state, detail = "ok", "Every expected report has arrived."
    return {
        "state": state,
        "detail": detail,
        "due": due,
        "late": late,
        "missing": missing,
        "untracked_customers": untracked_customers,
        "expected_customers": int(expected_customers),
        "newest_received": None if received is None else received.isoformat(),
        "days_since_newest": days,
    }


def file_health(root: Path | None, *, now: datetime) -> dict[str, Any]:
    status = read_json(None if root is None else root / "always-on" / "status.json")
    backup = read_json(None if root is None else root / "backups" / "last_backup.json")
    restore = read_json(None if root is None else root / "backups" / "last_restore.json")
    return {
        "services": services_health(status, now=now),
        "backups": backups_health(backup, restore, now=now),
    }

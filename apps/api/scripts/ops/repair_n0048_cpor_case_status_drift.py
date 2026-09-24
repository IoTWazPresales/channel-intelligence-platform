"""N-0048 repair: ``cpor_case.workflow_status`` drifted from ``status`` (BACKLOG-139).

Owner column is ``status`` (lifecycle.py; every reader filters on it). ``workflow_status``
is its projection, ``workflow_status_for(status)``: ``proposed`` -> ``pending_approval``,
every other status -> itself. Rows whose ``workflow_status`` differs from the projection
get the projected value; ``status`` is never changed. Each repaired row gets one
``cpor_case_event`` (``workflow_status_repair``, before/after in the payload), and the
before-values are written to ``.eif/audit/PROGRAMME_20260924/n0048/``.
``updated_at`` is left as is (the lifecycle did not move).

Idempotent: a second run changes 0 rows.

Default is a DRY RUN (transaction rolled back). ``--apply`` commits. ``--expect-db``
must equal ``current_database()`` or nothing runs.

Ready-for-cip (Warren runs, from apps/api):
    .venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip
    .venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from app.services.cpor.lifecycle import workflow_status_for  # noqa: E402

REPAIR_TAG = "N-0048"
EVENT_TYPE = "workflow_status_repair"
EVIDENCE_DIR = REPO_ROOT / ".eif" / "audit" / "PROGRAMME_20260924" / "n0048"

_ROWS_SQL = """
SELECT id, case_code, origin, status, workflow_status, updated_at
FROM cpor_case
ORDER BY id
"""

_UPDATE_SQL = text(
    "UPDATE cpor_case SET workflow_status = :new WHERE id = :id AND workflow_status IS NOT DISTINCT FROM :old"
)
_EVENT_SQL = text(
    "INSERT INTO cpor_case_event (case_id, event_type, actor, payload_json, created_at) "
    "VALUES (:case_id, :event_type, :actor, CAST(:payload AS jsonb), now())"
)


def plan_repair(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One change per row whose ``workflow_status`` is not the projection of ``status``."""
    changes: list[dict[str, Any]] = []
    for r in rows:
        want = workflow_status_for(str(r["status"]))
        if r["workflow_status"] != want:
            changes.append(
                {
                    "id": int(r["id"]),
                    "case_code": r["case_code"],
                    "origin": r["origin"],
                    "status": r["status"],
                    "workflow_status_before": r["workflow_status"],
                    "workflow_status_after": want,
                    "updated_at": r["updated_at"],
                }
            )
    return changes


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "cpor_case_rows": len(rows),
        "status_ne_workflow_status": sum(1 for r in rows if r["status"] != r["workflow_status"]),
        "workflow_status_ne_projection": len(plan_repair(rows)),
    }


def _rows(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(_ROWS_SQL)).mappings()]


def apply_changes(conn: Connection, changes: list[dict[str, Any]], *, actor: str) -> int:
    n = 0
    for c in changes:
        res = conn.execute(
            _UPDATE_SQL, {"id": c["id"], "new": c["workflow_status_after"], "old": c["workflow_status_before"]}
        )
        if res.rowcount != 1:
            continue
        n += 1
        conn.execute(
            _EVENT_SQL,
            {
                "case_id": c["id"],
                "event_type": EVENT_TYPE,
                "actor": actor,
                "payload": json.dumps(
                    {
                        "repair": REPAIR_TAG,
                        "backlog": "BACKLOG-139",
                        "status": c["status"],
                        "workflow_status_before": c["workflow_status_before"],
                        "workflow_status_after": c["workflow_status_after"],
                    }
                ),
            },
        )
    return n


def _write_before(db: str, changes: list[dict[str, Any]], *, apply: bool) -> Path | None:
    if not changes:
        return None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = EVIDENCE_DIR / f"before_{db}_{'apply' if apply else 'dryrun'}_{stamp}.json"
    path.write_text(json.dumps({"database": db, "apply": apply, "rows": changes}, indent=2, default=str), encoding="utf-8")
    return path


def run(conn: Connection, *, apply: bool, actor: str = f"ops:{REPAIR_TAG}") -> dict[str, Any]:
    """Run inside the caller's transaction. Caller commits or rolls back."""
    db = conn.execute(text("SELECT current_database()")).scalar()
    print("current_database() =", db)
    rows = _rows(conn)
    before = counts(rows)
    changes = plan_repair(rows)
    print("before:", json.dumps(before))
    for c in changes:
        print(
            f"  id={c['id']} {c['case_code']} origin={c['origin']} status={c['status']}: "
            f"workflow_status {c['workflow_status_before']} -> {c['workflow_status_after']}"
        )
    before_path = _write_before(str(db), changes, apply=apply)
    if before_path:
        print("before-values written:", before_path)
    print("current_database() before write =", conn.execute(text("SELECT current_database()")).scalar())
    written = apply_changes(conn, changes, actor=actor)
    after = counts(_rows(conn))
    print("rows updated:", written)
    print("after:", json.dumps(after))
    print("mode:", "APPLY (commit)" if apply else "DRY RUN (rollback)")
    return {"database": db, "before": before, "after": after, "changes": len(changes), "written": written}


def _rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--expect-db", required=True, help="must equal current_database()")
    ap.add_argument("--db", default=None, help="database name to connect to (default: settings DB)")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    sync = get_settings().database_url_sync
    if args.db:
        sync = _rewrite_dbname(sync, args.db)
    engine = create_engine(sqlalchemy_sync_engine_url(sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database() =", db)
        if db != args.expect_db:
            print(f"STOP: current_database() is {db}, expected {args.expect_db}")
            return 2
        # SQLAlchemy 2 autobegins one transaction on the first execute above.
        run(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Close stale open-order facts against the newest shipment report in each scope.

Dry run is the default and only runs SELECT. ``--apply`` writes one transaction:
reclassify shipped facts with no ship-confirm date to open_order, close open facts
that are not on the newest dated report of their scope, and write one
platform_audit_event. ``--expect-db`` must match ``current_database()``.

Do not pass ``cip`` until Warren says to run against cip.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session_sync import SessionLocal  # noqa: F401  (installs product-line scope)
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.services.imports.shipment_open_book import (
    close_against_newest_reports,
    preview_unconfirmed_shipped_ids,
    reclassify_unconfirmed_shipped,
    write_open_book_audit,
)
from app.services.supply_overview import _ISO_WEEK_START_SAST, _TODAY_SAST, _headline_sql

_BOOK_SQL = """
SELECT
  count(*) FILTER (WHERE lower(line_state) = 'open_order') AS open_lines,
  coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'open_order'), 0) AS open_units,
  count(*) FILTER (WHERE lower(line_state) = 'shipped') AS shipped_lines,
  coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'shipped'), 0) AS shipped_units,
  coalesce(sum(quantity) FILTER (
    WHERE lower(line_state) = 'shipped' AND ship_confirm_date IS NOT NULL
  ), 0) AS shipped_confirmed_units,
  coalesce(sum(quantity) FILTER (
    WHERE lower(line_state) = 'shipped' AND pod_date IS NOT NULL
  ), 0) AS shipped_landed_units,
  count(*) FILTER (WHERE lower(line_state) = 'closed_shipped') AS closed_shipped_lines,
  coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'closed_shipped'), 0) AS closed_shipped_units,
  count(*) FILTER (WHERE lower(line_state) = 'closed_disappeared') AS closed_disappeared_lines,
  coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'closed_disappeared'), 0) AS closed_disappeared_units
FROM fact_inbound_shipment
"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _engine(db_name: str):
    raw = make_url(get_settings().database_url_sync).set(database=db_name)
    return create_engine(sqlalchemy_sync_engine_url(raw.render_as_string(hide_password=False)))


def _measure(db: Session) -> dict[str, Any]:
    book = {
        key: _jsonable(value)
        for key, value in db.execute(text(_BOOK_SQL)).mappings().one().items()
    }
    headline = {
        key: _jsonable(value)
        for key, value in db.execute(
            text(_headline_sql(_TODAY_SAST, _ISO_WEEK_START_SAST)),
            {"tenant": "default"},
        ).mappings().one().items()
    }
    return {"book": book, "supply_headline": headline}


def _kinds(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "closed_shipped": sum(1 for row in rows if row["line_state"] == "closed_shipped"),
        "closed_disappeared": sum(1 for row in rows if row["line_state"] == "closed_disappeared"),
    }


def execute(db_name: str, *, apply: bool) -> dict[str, Any]:
    """Read, or apply, the open-book close. Raises SystemExit on a refused database or a count mismatch."""
    if (db_name or "").strip().lower() == "cip" and apply:
        print("apply target is cip; continuing because --expect-db cip was passed")
    engine = _engine(db_name)
    db = Session(engine)
    committed = False
    try:
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        current = db.execute(text("SELECT current_database()")).scalar()
        if current != db_name:
            raise SystemExit(f"refusing: current_database() is {current!r}, expected {db_name!r}")
        before = _measure(db)
        planned_reclass = preview_unconfirmed_shipped_ids(db)
        planned_close = close_against_newest_reports(db, apply=False)
        planned_kinds = _kinds(planned_close)
        if not apply:
            result = {
                "database": current,
                "apply": False,
                "before": before,
                "reclassified_unconfirmed_shipped": len(planned_reclass),
                "would_close": len(planned_close),
                **planned_kinds,
            }
            print(json.dumps(result, indent=2, default=str))
            return result

        reclassed = reclassify_unconfirmed_shipped(db)
        if set(reclassed) != set(planned_reclass):
            raise SystemExit(
                f"reclass count mismatch: planned {len(planned_reclass)} returning {len(reclassed)}"
            )
        closed = close_against_newest_reports(db, apply=True)
        if {int(row["id"]) for row in closed} != {int(row["id"]) for row in planned_close}:
            raise SystemExit(
                f"close count mismatch: planned {len(planned_close)} returning {len(closed)}"
            )
        if _kinds(closed) != planned_kinds:
            raise SystemExit("close kind mismatch between preview and update")
        report_date = date.fromisoformat(closed[0]["report_date"]) if closed else date.today()
        job_id = int(closed[0]["closing_job_id"]) if closed else 0
        if closed or reclassed:
            write_open_book_audit(
                db,
                tenant_id=str(closed[0]["tenant_id"]) if closed else "default",
                job_id=job_id,
                closed=closed,
                report_date=report_date,
                reclassified_ids=reclassed,
            )
        after = _measure(db)
        db.commit()
        committed = True
        result = {
            "database": current,
            "apply": True,
            "before": before,
            "after": after,
            "reclassified_unconfirmed_shipped": len(reclassed),
            "closed": len(closed),
            **_kinds(closed),
        }
        print(json.dumps(result, indent=2, default=str))
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        if not committed:
            db.rollback()
        db.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-db", required=True, help="Abort unless current_database() matches")
    parser.add_argument("--apply", action="store_true", help="Write the close. Default is a read-only preview")
    args = parser.parse_args(argv)
    execute(args.expect_db.strip(), apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""CLI for shipment change-event derivation (Plan D phase 4)."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_change_events import (
    derive_change_events,
    group_events_by_line,
    summarize_change_events,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=None, help="Quarter filter e.g. 26Q2")
    parser.add_argument("--distributor-id", type=int, default=None)
    parser.add_argument("--operating-unit", default=None)
    parser.add_argument("--event-type", action="append", default=None)
    parser.add_argument("--line-identity-key", default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--chains", action="store_true", help="Include per-line event chains")
    args = parser.parse_args()

    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            print(f"Refusing: current_database()={dbname!r}", file=sys.stderr)
            return 2

        et = {t.strip().lower() for t in args.event_type} if args.event_type else None
        events = derive_change_events(
            db,
            period=args.period,
            distributor_id=args.distributor_id,
            operating_unit=args.operating_unit,
            event_types=et,
            line_identity_key=args.line_identity_key,
            limit=args.limit,
        )
        payload: dict = {
            "database": str(dbname),
            "summary": summarize_change_events(events),
            "total": len(events),
            "events": [e.to_dict() for e in events],
        }
        if args.chains:
            payload["chains_by_line_identity_key"] = group_events_by_line(events)

    print(json.dumps(payload["summary"], indent=2))
    print(f"total events: {payload['total']}")

    if args.json_out:
        from pathlib import Path

        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"JSON written: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Backfill sticky POD onto fact_inbound_shipment (P1-D004 / BACKLOG-088).

Default is dry-run. Pass --apply to write (requires current_database() = cip).

Strategy: for shipped facts with NULL pod_date, take the latest non-null pod_date
from active shipment_evidence_line rows that share the same fact_upsert_key
(computed via fact_upsert_key_for_evidence_values). Also set status='received'.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.models.facts import FactInboundShipment  # noqa: E402
from app.models.shipment_evidence import ShipmentEvidenceLine  # noqa: E402
from app.services.imports.shipment_inbound_facts import (  # noqa: E402
    _row_values_from_evidence,
)


def _database_url() -> str:
    env = Path(__file__).resolve().parents[2] / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            return url.replace("+asyncpg", "+psycopg").replace("+psycopg2", "+psycopg")
    raise SystemExit("DATABASE_URL missing in apps/api/.env")


def _best_pod_by_fact_key(db: Session) -> dict[str, date]:
    lines = db.scalars(
        select(ShipmentEvidenceLine).where(
            ShipmentEvidenceLine.pod_date.is_not(None),
            ShipmentEvidenceLine.corpus_superseded_at.is_(None),
        )
    ).all()
    best: dict[str, date] = {}
    for line in lines:
        vals = _row_values_from_evidence(line)
        key = str(vals["fact_upsert_key"])
        pod = line.pod_date
        if pod is None:
            continue
        prev = best.get(key)
        if prev is None or pod > prev:
            best[key] = pod
    return best


def run(*, apply: bool) -> dict[str, int]:
    eng = create_engine(_database_url())
    SessionLocal = sessionmaker(bind=eng)
    with SessionLocal() as db:
        db_name = db.execute(text("select current_database()")).scalar()
        if db_name != "cip":
            raise SystemExit(f"refusing: current_database()={db_name!r} (want cip)")
        best = _best_pod_by_fact_key(db)
        null_facts = db.scalars(
            select(FactInboundShipment).where(
                FactInboundShipment.pod_date.is_(None),
                FactInboundShipment.line_state == "shipped",
            )
        ).all()
        updates: list[tuple[int, date]] = []
        for fact in null_facts:
            key = str(fact.fact_upsert_key or "")
            pod = best.get(key)
            if pod is not None:
                updates.append((int(fact.id), pod))
        stats = {
            "shipped_null_before": len(null_facts),
            "evidence_pod_keys": len(best),
            "would_update": len(updates),
        }
        print(stats)
        if not apply:
            print("dry-run only (pass --apply to write)")
            return stats
        by_pod: dict[date, list[int]] = defaultdict(list)
        for fid, pod in updates:
            by_pod[pod].append(fid)
        n = 0
        for pod, ids in by_pod.items():
            for i in range(0, len(ids), 500):
                chunk = ids[i : i + 500]
                db.execute(
                    text(
                        """
                        UPDATE fact_inbound_shipment
                        SET pod_date = :pod, status = 'received', updated_at = now()
                        WHERE id = ANY(:ids) AND pod_date IS NULL
                        """
                    ),
                    {"pod": pod, "ids": chunk},
                )
                n += len(chunk)
        db.commit()
        after = db.execute(
            text(
                """
                SELECT count(*) FROM fact_inbound_shipment
                WHERE lower(coalesce(line_state,'')) = 'shipped' AND pod_date IS NULL
                """
            )
        ).scalar()
        stats["updated"] = n
        stats["shipped_null_after"] = int(after or 0)
        print({"updated": n, "shipped_null_after": after})
        return stats


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    run(apply=bool(args.apply))


if __name__ == "__main__":
    main()

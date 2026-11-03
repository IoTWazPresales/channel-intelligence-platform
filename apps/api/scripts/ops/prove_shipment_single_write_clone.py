#!/usr/bin/env python3
"""D4 clone proof: counts before and after the single-write cutover. Read only. Do not run on cip.

Warren runs this on a copy of cip, twice. The first run is before migration ``20261103_0052`` and
before the D4 code. The second run is after the migration on that copy (the code is not required
for the counts). The line-payload checksum must be the same both times: D4 stops writing the
columns and does not clear them. ``lines_with_no_observation`` must be 0 before the code is
deployed, because apply then refuses a line that has no observation.

Nothing here writes, migrates, or connects to a database named cip.

Usage (from apps/api, against the clone — not cip):

  python scripts/ops/prove_shipment_single_write_clone.py --expect-db cip_d4_clone

Steps:

1. Copy cip to a new database (``pg_dump`` / ``pg_restore``, or the usual clone). Do not drop or
   migrate cip.
2. Point ``DATABASE_URL_SYNC`` at the copy. Run this script. Save the output. That is the before.
3. On the copy only, upgrade to ``20261103_0052`` (down_revision ``20261102_0051``; the merge may
   renumber the file). Run this script again. Save the output. That is the after.
4. Compare. ``line_payload_checksum``, ``lines``, ``observations`` and ``facts`` stay the same.
   ``lines_with_no_observation`` stays 0. ``payload_differs_from_newest_observation`` is the rows
   whose line columns are not the newest observation (history, not a failure of this migration).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

from sqlalchemy import create_engine, text


def _refuse_cip(name: str) -> None:
    if (name or "").strip().lower() == "cip":
        sys.exit("refusing: this script does not run on cip")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only D4 counts on a clone of cip")
    parser.add_argument("--expect-db", required=True, help="database name this process must be connected to")
    args = parser.parse_args()
    expect = args.expect_db.strip()
    _refuse_cip(expect)
    url = os.environ.get("DATABASE_URL_SYNC", "").strip()
    if not url:
        sys.exit("DATABASE_URL_SYNC is not set")
    if url.rstrip("/").endswith("/cip"):
        sys.exit("refusing: DATABASE_URL_SYNC ends in /cip")
    engine = create_engine(url)
    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
        _refuse_cip(str(current))
        if str(current) != expect:
            sys.exit(f"refusing: current_database() is {current}, expected {expect}")
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        lines = conn.execute(text("SELECT count(*) FROM shipment_evidence_line")).scalar_one()
        observations = conn.execute(text("SELECT count(*) FROM shipment_evidence_observation")).scalar_one()
        facts = conn.execute(text("SELECT count(*) FROM fact_inbound_shipment")).scalar_one()
        no_obs = conn.execute(
            text(
                """
                SELECT count(*) FROM shipment_evidence_line l
                WHERE NOT EXISTS (
                    SELECT 1 FROM shipment_evidence_observation o WHERE o.evidence_line_id = l.id
                )
                """
            )
        ).scalar_one()
        differs = conn.execute(
            text(
                """
                SELECT count(*) FROM shipment_evidence_line l
                JOIN LATERAL (
                    SELECT o.report_type, o.line_state, o.item_code, o.quantity, o.customer_po, o.pod_date
                    FROM shipment_evidence_observation o
                    WHERE o.evidence_line_id = l.id
                    ORDER BY o.id DESC
                    LIMIT 1
                ) obs ON TRUE
                WHERE l.report_type IS DISTINCT FROM obs.report_type
                   OR l.line_state IS DISTINCT FROM obs.line_state
                   OR l.item_code IS DISTINCT FROM obs.item_code
                   OR l.quantity IS DISTINCT FROM obs.quantity
                   OR l.customer_po IS DISTINCT FROM obs.customer_po
                   OR l.pod_date IS DISTINCT FROM obs.pod_date
                """
            )
        ).scalar_one()
        checksum = conn.execute(
            text(
                """
                SELECT md5(coalesce(string_agg(row_txt, ',' ORDER BY id), ''))
                FROM (
                    SELECT id,
                           concat_ws('|', id::text, report_type, line_state, item_code,
                                     quantity::text, customer_po, pod_date::text) AS row_txt
                    FROM shipment_evidence_line
                ) s
                """
            )
        ).scalar_one()
    digest = hashlib.sha256(f"{lines}|{observations}|{facts}|{checksum}".encode()).hexdigest()[:16]
    print(f"database={current}")
    print(f"alembic={revision}")
    print(f"lines={int(lines)}")
    print(f"observations={int(observations)}")
    print(f"facts={int(facts)}")
    print(f"lines_with_no_observation={int(no_obs)}")
    print(f"payload_differs_from_newest_observation={int(differs)}")
    print(f"line_payload_checksum={checksum}")
    print(f"bundle={digest}")


if __name__ == "__main__":
    main()

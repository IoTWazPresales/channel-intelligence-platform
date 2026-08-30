"""SESSION D read-only evidence queries on cip (stdout only)."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402


def run_query(session, sql: str, label: str) -> None:
    print(f"--- {label} ---")
    print(sql.strip())
    rows = session.execute(text(sql)).fetchall()
    for row in rows:
        print(row)
    if not rows:
        print("(no rows)")
    print()


def main() -> None:
    print("=== SESSION D read-only cip evidence ===\n")
    with SessionLocal() as session:
        run_query(session, "SELECT current_database()", "6f.1 current_database")
        run_query(
            session,
            """
            SELECT c.id AS case_id, c.commercial_status, c.period_label
            FROM commercial_lineup_case c
            WHERE c.id = 1016
               OR c.id IN (
                 SELECT DISTINCT cll.case_id
                 FROM commercial_lineup_line cll
                 WHERE cll.distributor_attribution_status = 'token_proposed'
               )
            LIMIT 10
            """,
            "6f.1 cases (1016 or token_proposed)",
        )
        run_query(
            session,
            """
            SELECT id, case_id, distributor_attribution_status, distributor_id, product_id, quantity_units
            FROM commercial_lineup_line
            WHERE case_id IN (
              SELECT c.id FROM commercial_lineup_case c
              WHERE c.id = 1016
                 OR c.id IN (
                   SELECT DISTINCT cll.case_id
                   FROM commercial_lineup_line cll
                   WHERE cll.distributor_attribution_status = 'token_proposed'
                 )
            )
            ORDER BY case_id, id
            LIMIT 30
            """,
            "6f.1 lineup lines",
        )
        run_query(
            session,
            """
            SELECT distributor_attribution_status, count(*)
            FROM commercial_lineup_line
            WHERE distributor_attribution_status IS NOT NULL
            GROUP BY distributor_attribution_status
            ORDER BY count(*) DESC
            """,
            "6f.1 status distribution",
        )
        run_query(
            session,
            """
            SELECT id, case_id, distributor_attribution_status, distributor_id, product_id, quantity_units
            FROM commercial_lineup_line
            WHERE case_id = 1016
            ORDER BY id
            LIMIT 30
            """,
            "6f.1 case 1016 lines (explicit)",
        )
        run_query(
            session,
            """
            SELECT id, created_at, entity_type, action, payload_json
            FROM steward_audit_event
            WHERE entity_type ILIKE '%distributor%'
               OR payload_json::text ILIKE '%attribution%'
            ORDER BY created_at DESC
            LIMIT 10
            """,
            "6f.4 recent steward_audit_event (pre-action baseline)",
        )
        run_query(
            session,
            """
            SELECT line_state, count(*) AS cnt
            FROM fact_inbound_shipment
            GROUP BY line_state
            ORDER BY line_state
            """,
            "7.4 fact_inbound_shipment by line_state",
        )

    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.inbound_lineup_quarter import lineup_quarter_summary

    async def _summary() -> None:
        async with AsyncSessionLocal() as db:
            for pq in ("26Q1", "26Q2", "25Q4"):
                try:
                    out = await lineup_quarter_summary(db, plan_quarter=pq)
                except Exception as exc:
                    print(f"--- 7.4 lineup_quarter_summary {pq} ERROR ---")
                    print(exc)
                    print()
                    continue
                if out.get("data_unavailable"):
                    print(f"--- 7.4 lineup_quarter_summary {pq} ---")
                    print(out)
                    print()
                    continue
                print(f"--- 7.4 lineup_quarter_summary {pq} ---")
                for k in (
                    "plan_quarter",
                    "plan_quarter_label",
                    "landed_this_quarter_units",
                    "shipped_not_landed_units",
                    "landed_units",
                    "shipped_units",
                    "planned_units",
                ):
                    print(f"{k}: {out.get(k)}")
                print()

    print("=== 7.4 service-layer lineup_quarter_summary spot-check ===\n")
    asyncio.run(_summary())


if __name__ == "__main__":
    main()

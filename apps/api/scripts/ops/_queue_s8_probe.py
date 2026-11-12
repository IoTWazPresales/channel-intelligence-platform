"""Read-only footprint of Compuspeed (1152) and Syntech (4145) on the settings database.

Prints identity, FK counts, aliases, and whether any audit payload stores row ids.
Does not write.
"""
from __future__ import annotations

import sys
from pathlib import Path

WORKTREE_API = Path(__file__).resolve().parents[2]
MAIN_API = Path(__file__).resolve().parents[6] / "apps" / "api"
sys.path.insert(0, str(MAIN_API))
sys.path.insert(0, str(WORKTREE_API))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from app.services.customer_full_repoint import count_customer_fk_refs  # noqa: E402

IDS = (1, 1152, 4145)


def main() -> int:
    url = sqlalchemy_sync_engine_url(get_settings().database_url_sync)
    engine = create_engine(url)
    with Session(engine) as db:
        name = db.execute(text("SELECT current_database()")).scalar()
        print("current_database()", name)
        print("alembic", [r[0] for r in db.execute(text("SELECT version_num FROM alembic_version"))])
        print("customers")
        for row in db.execute(
            text(
                """
                SELECT id, code, name, customer_status, merged_into_customer_id
                FROM dim_customer
                WHERE id = ANY(:ids)
                ORDER BY id
                """
            ),
            {"ids": list(IDS)},
        ):
            print(" ", tuple(row))
        print("distributors")
        for row in db.execute(
            text(
                """
                SELECT id, code, name
                FROM dim_distributor
                WHERE id IN (12, 51)
                ORDER BY id
                """
            )
        ):
            print(" ", tuple(row))
        for cid in (1152, 4145, 1):
            counts = count_customer_fk_refs(db, cid)
            print("fk", cid, "tables", len(counts), "rows", sum(counts.values()))
            for key, n in sorted(counts.items()):
                print(" ", key, n)
        print("customer_aliases")
        for row in db.execute(
            text(
                """
                SELECT id, customer_id, status, normalized_token
                FROM customer_source_token_alias
                WHERE customer_id = ANY(:ids)
                   OR normalized_token ILIKE '%compuspeed%'
                   OR normalized_token ILIKE '%syntech%'
                ORDER BY id
                """
            ),
            {"ids": [1152, 4145, 1]},
        ):
            print(" ", tuple(row))
        print("distributor_aliases")
        for row in db.execute(
            text(
                """
                SELECT id, distributor_id, status, normalized_token
                FROM distributor_source_token_alias
                WHERE distributor_id IN (12, 51)
                   OR normalized_token ILIKE '%compuspeed%'
                   OR normalized_token ILIKE '%syntech%'
                ORDER BY id
                """
            )
        ):
            print(" ", tuple(row))
        print("sellout_by_distributor")
        for row in db.execute(
            text(
                """
                SELECT distributor_id, count(*)
                FROM fact_sales_sellout
                WHERE distributor_id IN (12, 51)
                GROUP BY distributor_id
                ORDER BY distributor_id
                """
            )
        ):
            print(" ", tuple(row))
        print("audit_actions")
        for row in db.execute(
            text(
                """
                SELECT id, created_at, action, target_dim, target_id,
                       jsonb_typeof(payload_json) AS kind,
                       (SELECT count(*) FROM jsonb_object_keys(payload_json)) AS keys
                FROM steward_audit_event
                WHERE target_id IN (1152, 4145, 12, 51)
                   OR entity_token ILIKE '%compuspeed%'
                   OR entity_token ILIKE '%syntech%'
                ORDER BY id
                """
            )
        ):
            print(" ", tuple(row))
        db.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only check that a planner with no matching line sees no shipment-evidence current rows.

Prints counts and booleans only. current_database() is printed first.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import os

os.chdir(ROOT / "apps" / "api")
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    url = settings.database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        db = conn.execute(text("select current_database()")).scalar_one()
        print("database", db)
        if db != "cip":
            raise SystemExit("refusing non-cip")
        conn.execute(text("SET default_transaction_read_only = on"))
        viewdef = conn.execute(
            text("select pg_get_viewdef('shipment_evidence_current'::regclass)")
        ).scalar_one()
        opts = conn.execute(
            text("select reloptions from pg_class where relname = 'shipment_evidence_current'")
        ).scalar_one()
        print("pick_fn", "cip_sev_current_observation_ids" in viewdef)
        print("security_invoker", bool(opts) and any("security_invoker=true" in str(x) for x in opts))
        rev = conn.execute(text("select version_num from alembic_version")).scalar_one()
        print("alembic", rev)

        def scoped(read: str, role: str) -> int:
            conn.execute(text("BEGIN"))
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(
                text(
                    "SELECT set_config('cip.product_lines', :r, true), "
                    "set_config('cip.editable_product_lines', '!', true), "
                    "set_config('cip.request_role', :role, true)"
                ),
                {"r": read, "role": role},
            )
            n = int(conn.execute(text("select count(*) from shipment_evidence_current")).scalar_one())
            conn.execute(text("ROLLBACK"))
            return n

        print("planner_no_line", scoped("!", "planner"))
        line = conn.execute(
            text(
                "select product_line from dim_product "
                "where product_line is not null and product_line <> '' "
                "group by product_line order by count(*) desc limit 1"
            )
        ).scalar_one()
        own = scoped(line, "planner")
        conn.execute(text("BEGIN"))
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(
            text(
                "SELECT set_config('cip.product_lines', :r, true), "
                "set_config('cip.editable_product_lines', '!', true), "
                "set_config('cip.request_role', 'planner', true)"
            ),
            {"r": line},
        )
        other = int(
            conn.execute(
                text(
                    """
                    select count(*) from shipment_evidence_current c
                    join dim_product p on p.id = c.product_id
                    where p.product_line is distinct from :line
                    """
                ),
                {"line": line},
            ).scalar_one()
        )
        null_product = int(
            conn.execute(
                text("select count(*) from shipment_evidence_current where product_id is null")
            ).scalar_one()
        )
        conn.execute(text("ROLLBACK"))
        print("planner_one_line_rows", own)
        print("planner_one_line_other_product_lines", other)
        print("planner_one_line_null_product", null_product)
        conn.execute(text("BEGIN"))
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(
            text(
                "SELECT set_config('cip.product_lines', :r, true), "
                "set_config('cip.editable_product_lines', '!', true), "
                "set_config('cip.request_role', 'planner', true)"
            ),
            {"r": line},
        )
        row = conn.execute(
            text(
                """
                select
                  count(*) filter (
                    where m.inherited_product_id is not null
                      and p.product_line = current_setting('cip.product_lines', true)
                  ) as inherited_this_line,
                  count(*) filter (
                    where m.inherited_product_id is not null
                      and p.product_line is distinct from current_setting('cip.product_lines', true)
                  ) as inherited_other_line,
                  count(*) filter (where m.inherited_product_id is null) as no_lineage
                from shipment_evidence_current c
                left join cip_sev_observation_lineage() m on m.row_id = c.id
                left join dim_product p on p.id = m.inherited_product_id
                where c.product_id is null
                """
            )
        ).one()
        conn.execute(text("ROLLBACK"))
        print("null_inherited_this_line", int(row.inherited_this_line))
        print("null_inherited_other_line", int(row.inherited_other_line))
        print("null_no_lineage", int(row.no_lineage))
        email = conn.execute(
            text(
                """
                select channel, status, count(*)
                from report_delivery
                where channel = 'email'
                group by channel, status
                """
            )
        ).all()
        print("email_deliveries", [(r[0], r[1], int(r[2])) for r in email] or "none")


if __name__ == "__main__":
    main()

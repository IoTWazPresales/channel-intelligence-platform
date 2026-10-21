"""N-0110: read-only numbers for the clone proof. usage: python numbers.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

import psycopg  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def url_for(db: str) -> str:
    s = get_settings()
    raw = (s.database_url_sync_migrate or s.database_url_sync).replace("postgresql+psycopg://", "postgresql://")
    return urlunparse(urlparse(raw)._replace(path="/" + db))


def numbers(db: str) -> dict:
    with psycopg.connect(url_for(db)) as conn:
        q = lambda sql: conn.execute(sql).fetchone()  # noqa: E731
        out = {"current_database": q("select current_database()")[0], "user": q("select current_user")[0]}
        out["rev"] = q("select version_num from alembic_version")[0]
        out["owners"] = dict(
            conn.execute(
                "select tablename, tableowner from pg_tables where tablename in "
                "('fact_customer_sellthrough','import_customer_sellthrough_staging_line','fact_inbound_shipment')"
            ).fetchall()
        )
        out["fact_rows"], out["fact_units"], out["fact_soh"], out["fact_soh_rows"] = q(
            "select count(*), coalesce(sum(units_sold),0), coalesce(sum(reported_soh),0), count(reported_soh) "
            "from fact_customer_sellthrough"
        )
        out["staging_rows"] = q("select count(*) from import_customer_sellthrough_staging_line")[0]
        out["shipments_pod_matched"] = q(
            "select count(*) from fact_inbound_shipment where pod_date is not null "
            "and resolved_customer_id is not null and lower(line_state) = 'shipped'"
        )[0]
        has_grain = q(
            "select count(*) from information_schema.columns where table_name='fact_customer_sellthrough' "
            "and column_name='period_grain'"
        )[0]
        out["grain_col"] = bool(has_grain)
        if has_grain:
            out["grain_not_null"] = q("select count(*) from fact_customer_sellthrough where period_grain is not null")[0]
        out["position_table"] = bool(q("select to_regclass('customer_stock_position')")[0])
        if out["position_table"]:
            out["positions"], out["compared"] = q(
                "select count(*), count(*) filter (where status = 'compared') from customer_stock_position"
            )
        return out


if __name__ == "__main__":
    for k, v in numbers(sys.argv[1]).items():
        print(f"{k}={v}")

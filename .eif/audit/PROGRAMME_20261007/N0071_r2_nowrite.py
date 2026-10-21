"""N-0071 round 2: read-only proof that no fact row was written today, plus the 10 partial lines' links."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings

u = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
    if u.startswith(pre):
        u = "postgresql+psycopg://" + u[len(pre):]
        break
PARTIAL = (299, 300, 302, 308, 100351, 100374, 100797, 100962, 100963, 107364)
with create_engine(u).connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database", c.execute(text("SELECT current_database()")).scalar())
    print("transaction_read_only", c.execute(text("SHOW transaction_read_only")).scalar())
    row = c.execute(
        text(
            "SELECT count(*), max(updated_at), max(created_at), "
            "count(*) FILTER (WHERE updated_at >= now() - interval '12 hours') "
            "FROM fact_inbound_shipment"
        )
    ).one()
    print("rows", row[0], "max_updated_at", row[1], "max_created_at", row[2], "updated_last_12h", row[3])
    print("db_now", c.execute(text("SELECT now()")).scalar())
    links = c.execute(
        text(
            "SELECT count(product_id), count(purchase_order_id), count(distributor_id) "
            "FROM fact_inbound_shipment WHERE id = ANY(:ids)"
        ),
        {"ids": list(PARTIAL)},
    ).one()
    print("partial lines: with product_id", links[0], "with purchase_order_id", links[1], "with distributor_id", links[2])
    c.rollback()

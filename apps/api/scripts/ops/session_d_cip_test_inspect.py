"""Inspect cip_test (read-only). Prints current_database() and row counts. No writes."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


def rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def redacted(url: str) -> str:
    p = urlparse(url)
    netloc = p.netloc
    if "@" in netloc:
        user, _, host = netloc.rpartition("@")
        user = user.split(":")[0]
        netloc = f"{user}:***@{host}"
    return urlunparse(p._replace(netloc=netloc))


def main() -> None:
    sync = get_settings().database_url_sync
    target = sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test"))
    print("target_url_redacted", redacted(target))
    engine = create_engine(target)
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip_test":
            print("STOP: not cip_test")
            return
        for sql, label in [
            ("SELECT count(*) FROM commercial_lineup_line", "line_count"),
            (
                "SELECT distributor_attribution_status, count(*) FROM commercial_lineup_line "
                "WHERE distributor_attribution_status IS NOT NULL "
                "GROUP BY distributor_attribution_status ORDER BY count(*) DESC",
                "status_dist",
            ),
            ("SELECT count(*) FROM steward_audit_event", "audit_count"),
            ("SELECT count(*) FROM commercial_lineup_case", "case_count"),
            ("SELECT count(*) FROM dim_distributor", "dist_count"),
            ("SELECT count(*) FROM dim_product", "product_count"),
            ("SELECT count(*) FROM dim_customer", "customer_count"),
            ("SELECT count(*) FROM fact_inbound_shipment", "fact_count"),
            ("SELECT id, email, role FROM app_user LIMIT 5", "users"),
            (
                "SELECT id, name FROM dim_customer WHERE lower(name) LIKE '%open%' LIMIT 5",
                "open_channel_customers",
            ),
        ]:
            print("---", label, "---")
            try:
                rows = conn.execute(text(sql)).fetchall()
                for r in rows:
                    print(tuple(r))
            except Exception as exc:
                print(type(exc).__name__, str(exc)[:300])


if __name__ == "__main__":
    main()

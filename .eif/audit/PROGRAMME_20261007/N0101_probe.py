"""N-0101 read-only probe: listing registry + observation counts on cip. SELECT only, read-only txn."""
from __future__ import annotations

import json
import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)

Q = {
    "listings_by_mkt_status": "SELECT marketplace, status, count(*) n FROM customer_listing GROUP BY 1,2 ORDER BY 1,2",
    "obs_by_mkt": """SELECT l.marketplace, count(o.id) n, max(o.fetched_at)::text latest
                     FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
                     GROUP BY 1 ORDER BY 1""",
    "obs_total": "SELECT count(*) n, max(id) max_id FROM listing_observation",
    "obs_since": """SELECT l.marketplace, o.http_status, o.parse_status, count(*) n,
                           min(o.fetched_at)::text first_at, max(o.fetched_at)::text last_at
                    FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
                    WHERE o.id > :since_id GROUP BY 1,2,3 ORDER BY 1,2,3""",
    "obs_since_flags": """SELECT l.marketplace,
                                 o.parse_flags->'status_transition'->>'reason' transition,
                                 o.parse_flags->>'reason' reason, count(*) n
                          FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
                          WHERE o.id > :since_id GROUP BY 1,2,3 ORDER BY 1,2,3""",
    "meta_failures": """SELECT marketplace, count(*) FILTER (WHERE (meta_json->>'consecutive_failures')::int > 0) with_failures
                        FROM customer_listing GROUP BY 1 ORDER BY 1""",
}

since_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
out: dict = {}
with eng.connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    out["current_database"] = conn.execute(text("SELECT current_database()")).scalar()
    print("current_database:", out["current_database"])
    for k, q in Q.items():
        if ":since_id" in q:
            if since_id is None:
                continue
            rows = conn.execute(text(q), {"since_id": since_id}).mappings().all()
        else:
            rows = conn.execute(text(q)).mappings().all()
        out[k] = [dict(r) for r in rows]
    conn.rollback()
print(json.dumps(out, indent=1, default=str))

"""N-0101 read-only probe 4: stored snapshot bytes per marketplace for observations after an id, and fetch order. SELECT only."""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
lo = int(sys.argv[1])
hi = int(sys.argv[2])
with eng.connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    print("current_database:", conn.execute(text("SELECT current_database()")).scalar())
    for r in conn.execute(text("""
        SELECT l.marketplace, count(*) n, sum(octet_length(o.raw_snapshot)) bytes,
               round(avg(octet_length(o.raw_snapshot))) avg_bytes
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :lo AND o.id <= :hi GROUP BY 1 ORDER BY 1"""), {"lo": lo, "hi": hi}).mappings():
        print(dict(r))
    seq = [m for (m,) in conn.execute(text("""
        SELECT l.marketplace FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :lo AND o.id <= :hi ORDER BY o.fetched_at LIMIT 12"""), {"lo": lo, "hi": hi})]
    print("first 12 fetches:", seq)
    print("table size:", conn.execute(text("SELECT pg_size_pretty(pg_total_relation_size('listing_observation'))")).scalar())
    conn.rollback()

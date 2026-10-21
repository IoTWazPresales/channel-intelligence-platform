"""N-0101 read-only probe 3: what the Amazon parse_failed pages are. SELECT only; prints marker counts, not page text."""
from __future__ import annotations

import gzip
import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
since = int(sys.argv[1]) if len(sys.argv) > 1 else 169
markers = ["captcha", "robot check", "automated access", "api-services-support", "productTitle", "a-price"]
with eng.connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    print("current_database:", conn.execute(text("SELECT current_database()")).scalar())
    rows = conn.execute(text("""
        SELECT o.parse_status, o.raw_snapshot FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :s AND l.marketplace = 'amazon'"""), {"s": since}).all()
    for status in ("ok", "parse_failed"):
        snaps = [gzip.decompress(b).decode("utf-8", "replace").lower() for st, b in rows if st == status and b]
        sizes = sorted(len(t) for t in snaps)
        print(status, "n", len(snaps), "size min/median/max", sizes[0] if sizes else None,
              sizes[len(sizes) // 2] if sizes else None, sizes[-1] if sizes else None)
        for m in markers:
            print("   ", m, sum(m.lower() in t for t in snaps))
    conn.rollback()

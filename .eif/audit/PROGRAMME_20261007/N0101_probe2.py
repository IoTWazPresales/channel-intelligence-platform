"""N-0101 read-only probe 2: the beat run's Takealot dead_link and Evetech out_of_stock results. SELECT only."""
from __future__ import annotations

import gzip
import json
import re
import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
since = int(sys.argv[1]) if len(sys.argv) > 1 else 169

with eng.connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    print("current_database:", conn.execute(text("SELECT current_database()")).scalar())
    rows = conn.execute(text("""
        SELECT o.listing_id, o.http_status, o.parse_flags->>'details_status' ds,
               o.parse_flags->>'fetch_reason' fr, o.parse_flags->>'ean_resolve' er,
               o.parse_flags->>'ean_result_count' erc,
               (l.url ~ 'PLID[0-9]') has_plid_url, (l.meta_json ? 'takealot_plid') has_known_plid,
               (SELECT count(*) FROM listing_observation p WHERE p.listing_id = o.listing_id AND p.id <= :s
                  AND p.parse_status = 'ok') prior_ok
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :s AND l.marketplace = 'takealot' AND o.parse_flags->'status_transition'->>'to' = 'dead_link'
    """), {"s": since}).mappings().all()
    agg: dict = {}
    for r in rows:
        k = (r["http_status"], r["ds"], r["fr"], r["er"], r["erc"], r["has_plid_url"], r["has_known_plid"], int(r["prior_ok"]) > 0)
        agg[k] = agg.get(k, 0) + 1
    print("takealot dead_link groups (http, details_status, fetch_reason, ean_resolve, ean_count, plid_in_url, known_plid, had_prior_ok): n")
    for k, n in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(" ", k, n)
    ex = conn.execute(text("""
        SELECT l.id, coalesce(l.meta_json->>'takealot_plid', substring(l.url from 'PLID([0-9]+)')) plid
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :s AND l.marketplace = 'takealot' AND o.parse_flags->'status_transition'->>'to' = 'dead_link'
          AND EXISTS (SELECT 1 FROM listing_observation p WHERE p.listing_id = l.id AND p.id <= :s AND p.parse_status = 'ok')
        ORDER BY l.id LIMIT 2"""), {"s": since}).mappings().all()
    print("dead with a prior ok observation (examples):", [dict(e) for e in ex])

    ev = conn.execute(text("""
        SELECT o.raw_snapshot, o.extracted_availability, o.parse_flags->>'method' m
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id > :s AND l.marketplace = 'evetech' AND o.parse_flags->'status_transition'->>'to' = 'out_of_stock'
        ORDER BY o.id"""), {"s": since}).mappings().all()
    stats: dict = {}
    for r in ev:
        t = gzip.decompress(r["raw_snapshot"]).decode("utf-8", "replace") if r["raw_snapshot"] else ""
        ld_avail = re.findall(r'"availability"\s*:\s*"(?:https?://schema\.org/)?(\w+)"', t)
        key = (r["m"], tuple(sorted(set(ld_avail))), bool(re.search(r"InStock|in stock", t, re.I)),
               len(re.findall(r"OutOfStock|out of stock", t, re.I)))
        stats[key] = stats.get(key, 0) + 1
    print("evetech out_of_stock (method, json-ld availability values, page also says in stock, out-of-stock mentions): n")
    for k, n in sorted(stats.items(), key=lambda kv: -kv[1])[:12]:
        print(" ", k, n)
    prior = conn.execute(text("""
        SELECT o.extracted_availability a, count(*) n FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.id <= :s AND l.marketplace = 'evetech' GROUP BY 1"""), {"s": since}).mappings().all()
    print("evetech availability before this run:", [dict(p) for p in prior])
    conn.rollback()

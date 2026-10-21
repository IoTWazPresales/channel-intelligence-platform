"""N-0101 GOV-008 verification (RUN-20261008-N0101-VER): read-only SELECTs on cip.

Run from apps/api with the venv python. Prints no secrets (no URL, no credentials).
"""

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
engine = create_engine(url)
SINCE = "2026-10-07 12:00:00+02:00"
TZ = "Africa/Johannesburg"

Q = {
    "db": "SELECT current_database(), current_setting('transaction_read_only')",
    "obs_by_half_hour_and_marketplace": f"""
        SELECT to_char(date_bin('30 minutes', o.fetched_at AT TIME ZONE '{TZ}', TIMESTAMP '2026-10-07 00:00'), 'MM-DD HH24:MI') AS slot,
               l.marketplace, count(*) AS n,
               to_char(min(o.fetched_at AT TIME ZONE '{TZ}'), 'HH24:MI:SS') AS first,
               to_char(max(o.fetched_at AT TIME ZONE '{TZ}'), 'HH24:MI:SS') AS last
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}'
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "obs_parse_status_since": f"""
        SELECT l.marketplace, o.parse_status, o.http_status, count(*)
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}'
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""",
    "listing_status_distribution": """
        SELECT marketplace, status, count(*) FROM customer_listing GROUP BY 1, 2 ORDER BY 1, 2""",
    "status_transitions_since": f"""
        SELECT l.marketplace, o.parse_flags->'status_transition'->>'reason' AS reason, count(*)
        FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' AND o.parse_flags ? 'status_transition'
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "site_paused_flags_since": f"""
        SELECT count(*) FROM listing_observation o
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' AND o.parse_flags ? 'site_paused'""",
    "http_403_429_since": f"""
        SELECT count(*) FROM listing_observation o
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' AND o.http_status IN (403, 429)""",
    "takealot_dead_link_failures": """
        SELECT coalesce((meta_json->>'consecutive_failures')::int, 0) AS consecutive_failures,
               count(*),
               to_char(min((meta_json->>'last_failure_at')::timestamptz AT TIME ZONE 'Africa/Johannesburg'), 'MM-DD HH24:MI') AS min_last_failure,
               to_char(max((meta_json->>'last_failure_at')::timestamptz AT TIME ZONE 'Africa/Johannesburg'), 'MM-DD HH24:MI') AS max_last_failure
        FROM customer_listing WHERE marketplace = 'takealot' AND status = 'dead_link'
        GROUP BY 1 ORDER BY 1""",
    "dead_link_obs_per_listing_since": f"""
        SELECT l.marketplace, n_obs, count(*) AS listings FROM (
            SELECT o.listing_id, count(*) AS n_obs FROM listing_observation o
            JOIN customer_listing l2 ON l2.id = o.listing_id AND l2.status = 'dead_link'
            WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' GROUP BY 1) x
        JOIN customer_listing l ON l.id = x.listing_id GROUP BY 1, 2 ORDER BY 1, 2""",
    "dead_link_obs_after_backoff": f"""
        SELECT count(*) FROM listing_observation o JOIN customer_listing l ON l.id = o.listing_id
        WHERE l.status = 'dead_link' AND o.fetched_at >= TIMESTAMPTZ '2026-10-08 08:00:00+02:00'""",
    "skipped_rows_since": f"""
        SELECT count(*) FROM listing_observation o
        WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' AND o.parse_status = 'skipped'""",
    "snapshot_mb_per_slot": f"""
        SELECT to_char(date_bin('30 minutes', o.fetched_at AT TIME ZONE '{TZ}', TIMESTAMP '2026-10-07 00:00'), 'MM-DD HH24:MI') AS slot,
               round(sum(octet_length(o.raw_snapshot))/1048576.0, 1) AS mb
        FROM listing_observation o WHERE o.fetched_at >= TIMESTAMPTZ '{SINCE}' GROUP BY 1 ORDER BY 1""",
}

with engine.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    for name, sql in Q.items():
        print(f"== {name}")
        for row in conn.execute(text(sql)).all():
            print("  ", tuple(row))
    conn.rollback()

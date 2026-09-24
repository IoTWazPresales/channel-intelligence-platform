"""N-0039 repair: Takealot listing URLs built from the report SKU (RC1/RC2/RC3).

R-a  Takealot rows with a resolved PLID (``meta_json ? 'takealot_plid'``):
     ``url`` -> the canonical product URL from the latest resolving observation, else
     ``https://www.takealot.com/x/PLID<plid>``. The replaced value is kept in
     ``meta_json.original_url``. ``meta_json.url_verified_at`` is stamped with the
     ``fetched_at`` of the observation that verified the PLID (HTTP 200, parse ok,
     EAN hit barcode/SKU-corroborated or PLID fetched directly) — evidence time, not now.
R-a-conflict  An R-a row whose product URL is already held by another listing of the
     same customer (two report SKUs resolving to one PLID; unique customer_id+url):
     URL left as is, not verified, ``meta_json.url_conflict_listing_id`` = the holder.
     No merge (lower id keeps the URL).
R-b  Takealot rows with no resolved PLID: flagged unverified
     (``meta_json.url_check = 'unverified'``, reason ``plid_unresolved``; any stale
     ``url_verified_at`` removed). Among them, rows whose latest real fetch was a REST
     404/410 and whose product has no EAN/UPC (so no EAN recovery is possible) become
     ``status = 'dead_link'`` (observed, never deleted), ``status_observed_at`` = that
     fetch time. Only ``active`` rows change status.

Idempotent: a second run changes 0 rows. Amazon and Evetech rows are not touched.

Default is a DRY RUN (transaction rolled back). ``--apply`` commits. ``--expect-db``
must equal ``current_database()`` or nothing runs.

Ready-for-cip (Warren runs, from apps/api):
    .venv/Scripts/python.exe scripts/ops/repair_n0039_takealot_listing_urls.py --expect-db cip
    .venv/Scripts/python.exe scripts/ops/repair_n0039_takealot_listing_urls.py --expect-db cip --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from app.services.listing_capture.auto_finder import takealot_product_url  # noqa: E402

REPAIR_TAG = "N-0039"

_COUNTS_SQL = """
SELECT
  count(*) FILTER (WHERE marketplace = 'takealot') AS takealot_rows,
  count(*) FILTER (WHERE marketplace = 'takealot' AND meta_json ? 'takealot_plid') AS takealot_resolved_plid,
  count(*) FILTER (WHERE marketplace = 'takealot' AND url ~ '^https://www\\.takealot\\.com/PLID[0-9]+$') AS takealot_bare_plid_url,
  count(*) FILTER (WHERE marketplace = 'takealot' AND url LIKE 'https://www.takealot.com/x/PLID%') AS takealot_x_plid_url,
  count(*) FILTER (WHERE marketplace = 'takealot' AND url ~ '^https://www\\.takealot\\.com/[^/]+/PLID[0-9]+$'
                     AND url NOT LIKE 'https://www.takealot.com/x/PLID%') AS takealot_slug_url,
  count(*) FILTER (WHERE meta_json ? 'original_url') AS with_original_url,
  count(*) FILTER (WHERE meta_json ? 'url_verified_at') AS with_url_verified_at,
  count(*) FILTER (WHERE meta_json->>'url_check' = 'unverified') AS flagged_unverified,
  count(*) FILTER (WHERE meta_json ? 'url_conflict_listing_id') AS url_conflict,
  count(*) FILTER (WHERE status = 'dead_link') AS dead_link,
  count(*) FILTER (WHERE status = 'active') AS active,
  count(*) FILTER (WHERE marketplace <> 'takealot') AS non_takealot_rows,
  md5(coalesce(string_agg(id::text || url || status || coalesce(meta_json::text, ''), '|' ORDER BY id)
      FILTER (WHERE marketplace <> 'takealot'), '')) AS non_takealot_fingerprint
FROM customer_listing
"""

# Resolving observation for the stored PLID: HTTP 200, parse ok, no fetch-side reason,
# PLID fetched directly (url_or_known) or EAN hit corroborated by barcode/SKU.
_RA_SQL = """
SELECT l.id, l.customer_id, l.url, l.meta_json, l.meta_json->>'takealot_plid' AS plid, v.canonical_url, v.fetched_at
FROM customer_listing l
LEFT JOIN LATERAL (
  SELECT o.parse_flags->>'canonical_url' AS canonical_url, o.fetched_at
  FROM listing_observation o
  WHERE o.listing_id = l.id
    AND o.http_status = 200
    AND o.parse_status = 'ok'
    AND o.parse_flags->>'resolved_plid' = l.meta_json->>'takealot_plid'
    AND o.parse_flags->>'reason' IS NULL
    AND coalesce(o.parse_flags->>'fetch_reason', '') = ''
    AND (o.parse_flags->>'plid_source' = 'url_or_known' OR o.parse_flags->>'corroboration' IS NOT NULL)
  ORDER BY o.fetched_at DESC, o.id DESC
  LIMIT 1
) v ON TRUE
WHERE l.marketplace = 'takealot' AND l.meta_json ? 'takealot_plid'
ORDER BY l.id
"""

_RB_SQL = """
SELECT l.id, l.url, l.status, l.meta_json,
       nullif(btrim(coalesce(p.ean, '')), '') IS NULL AND nullif(btrim(coalesce(p.upc, '')), '') IS NULL AS no_ean,
       last.http_status AS last_http_status, last.parse_status AS last_parse_status, last.fetched_at AS last_fetched_at
FROM customer_listing l
LEFT JOIN dim_product p ON p.id = l.product_id
LEFT JOIN LATERAL (
  SELECT o.http_status, o.parse_status, o.fetched_at
  FROM listing_observation o
  WHERE o.listing_id = l.id AND o.parse_status <> 'skipped'
  ORDER BY o.fetched_at DESC, o.id DESC
  LIMIT 1
) last ON TRUE
WHERE l.marketplace = 'takealot' AND NOT coalesce(l.meta_json ? 'takealot_plid', FALSE)
ORDER BY l.id
"""

_UPDATE_SQL = text(
    "UPDATE customer_listing SET url = :url, status = :status, status_observed_at = :status_observed_at, "
    "meta_json = CAST(:meta AS jsonb), updated_at = now() WHERE id = :id"
)


def _meta(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def counts(conn: Connection) -> dict[str, Any]:
    row = conn.execute(text(_COUNTS_SQL)).mappings().one()
    return dict(row)


def plan_repair(conn: Connection) -> list[dict[str, Any]]:
    """Return one change dict per row that must change (empty when already repaired)."""
    changes: list[dict[str, Any]] = []
    status_at = {
        int(r.id): r.status_observed_at
        for r in conn.execute(
            text("SELECT id, status_observed_at FROM customer_listing WHERE marketplace = 'takealot'")
        )
    }

    # (customer_id, url) -> listing id, all marketplaces: uq_customer_listing_customer_url.
    taken = {
        (int(r.customer_id), str(r.url)): int(r.id)
        for r in conn.execute(text("SELECT id, customer_id, url FROM customer_listing"))
    }

    for r in conn.execute(text(_RA_SQL)).mappings():
        meta = _meta(r["meta_json"])
        new_meta = dict(meta)
        new_url = takealot_product_url(r["plid"], canonical_url=r["canonical_url"])
        rule = "R-a"
        holder = taken.get((int(r["customer_id"]), new_url))
        if new_url != r["url"] and holder is not None and holder != int(r["id"]):
            # Two report SKUs of one customer resolve to the same PLID: the lower id
            # already holds the product URL. Do not rewrite, verify or merge; flag it.
            rule = "R-a-conflict"
            new_url = r["url"]
            new_meta["url_conflict_listing_id"] = holder
            new_meta.pop("url_verified_at", None)
        else:
            if new_url != r["url"]:
                new_meta.setdefault("original_url", r["url"])
                taken.pop((int(r["customer_id"]), str(r["url"])), None)
                taken[(int(r["customer_id"]), new_url)] = int(r["id"])
            if r["fetched_at"] is not None:
                new_meta["url_verified_at"] = r["fetched_at"].isoformat()
            new_meta.pop("url_conflict_listing_id", None)
        new_meta.pop("url_check", None)
        new_meta.pop("url_unverified_reason", None)
        if new_url != r["url"] or new_meta != meta:
            new_meta["url_repair"] = REPAIR_TAG
            changes.append(
                {
                    "rule": rule,
                    "id": int(r["id"]),
                    "url_before": r["url"],
                    "url": new_url,
                    "status": "active_or_unchanged",
                    "meta": new_meta,
                    "verified": rule == "R-a" and r["fetched_at"] is not None,
                }
            )

    for r in conn.execute(text(_RB_SQL)).mappings():
        meta = _meta(r["meta_json"])
        new_meta = dict(meta)
        new_meta["url_check"] = "unverified"
        new_meta["url_unverified_reason"] = "plid_unresolved"
        new_meta.pop("url_verified_at", None)
        status = r["status"]
        observed_at = status_at.get(int(r["id"]))
        dead = (
            status == "active"
            and r["no_ean"]
            and r["last_http_status"] in (404, 410)
            and r["last_parse_status"] != "ok"
        )
        if dead:
            status = "dead_link"
            observed_at = r["last_fetched_at"]
            new_meta["dead_link_reason"] = "rest_404_no_ean"
        if new_meta != meta or status != r["status"]:
            new_meta["url_repair"] = REPAIR_TAG
            changes.append(
                {
                    "rule": "R-b-dead" if dead else "R-b",
                    "id": int(r["id"]),
                    "url_before": r["url"],
                    "url": r["url"],
                    "status": status,
                    "status_observed_at": observed_at,
                    "meta": new_meta,
                }
            )
    return changes


def apply_changes(conn: Connection, changes: list[dict[str, Any]]) -> None:
    current = {
        int(r.id): (r.status, r.status_observed_at)
        for r in conn.execute(text("SELECT id, status, status_observed_at FROM customer_listing WHERE marketplace = 'takealot'"))
    }
    for c in changes:
        status, observed_at = current[c["id"]]
        if c["rule"] == "R-b-dead":
            status, observed_at = c["status"], c["status_observed_at"]
        conn.execute(
            _UPDATE_SQL,
            {
                "id": c["id"],
                "url": c["url"][:1024],
                "status": status,
                "status_observed_at": observed_at,
                "meta": json.dumps(c["meta"], default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)),
            },
        )


def run(conn: Connection, *, apply: bool) -> dict[str, Any]:
    """Run inside the caller's transaction. Caller commits or rolls back."""
    db = conn.execute(text("SELECT current_database()")).scalar()
    print("current_database() =", db)
    before = counts(conn)
    changes = plan_repair(conn)
    by_rule: dict[str, int] = {}
    for c in changes:
        by_rule[c["rule"]] = by_rule.get(c["rule"], 0) + 1
    print("before:", json.dumps(before, default=str))
    print("planned changes by rule:", json.dumps(by_rule))
    print("R-a verified stamps:", sum(1 for c in changes if c["rule"] == "R-a" and c.get("verified")))
    print("R-b-dead ids:", [c["id"] for c in changes if c["rule"] == "R-b-dead"])
    print("R-a-conflict:", [(c["id"], c["meta"].get("url_conflict_listing_id")) for c in changes if c["rule"] == "R-a-conflict"])
    for c in changes[:3]:
        if c["rule"] == "R-a":
            print(f"  sample R-a id={c['id']}: {c['url_before']} -> {c['url']}")
    print("current_database() before write =", conn.execute(text("SELECT current_database()")).scalar())
    apply_changes(conn, changes)
    after = counts(conn)
    print("after:", json.dumps(after, default=str))
    print("mode:", "APPLY (commit)" if apply else "DRY RUN (rollback)")
    return {"database": db, "before": before, "after": after, "by_rule": by_rule, "changes": len(changes)}


def _rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--expect-db", required=True, help="must equal current_database()")
    ap.add_argument("--db", default=None, help="database name to connect to (default: settings DB)")
    ap.add_argument("--schema", default=None, help="search_path schema (scratch proofs only)")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    sync = get_settings().database_url_sync
    if args.db:
        sync = _rewrite_dbname(sync, args.db)
    engine = create_engine(sqlalchemy_sync_engine_url(sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database() =", db)
        if db != args.expect_db:
            print(f"STOP: current_database() is {db}, expected {args.expect_db}")
            return 2
        if args.schema:
            conn.execute(text(f'SET search_path TO "{args.schema}"'))
        # SQLAlchemy 2 autobegins one transaction on the first execute above.
        run(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

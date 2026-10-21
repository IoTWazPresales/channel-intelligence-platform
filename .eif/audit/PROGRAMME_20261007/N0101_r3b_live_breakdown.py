"""N-0101 round 3 (continued): read-only breakdown of snapshot storage per run on cip. No writes.

Usage (from apps/api, PYTHONPATH=., venv python): N0101_r3b_live_breakdown.py <after_id>

Per run slot x marketplace x reason: rows, rows with a snapshot, bytes. Then, for every
observation stored as 'changed', which compared field differed from the listing's
previous successful observation (the same comparison record_observation makes).
The URL comes from get_settings().database_url_sync in-process; nothing secret is printed.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy import create_engine, text

from app.core.config import get_settings

SLOT = (
    "date_trunc('hour', o.fetched_at) + interval '30 min' * floor(extract(minute from o.fetched_at) / 30)"
)


def _pk(v):
    return None if v is None else str(Decimal(str(v)).quantize(Decimal("0.0001")))


def main() -> None:
    after = int(sys.argv[1])
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("transaction_read_only =", c.execute(text("show transaction_read_only")).scalar_one())
        rows = c.execute(
            text(
                f"""
                select {SLOT} as slot, l.marketplace,
                       coalesce(o.parse_flags->>'snapshot_stored', 'skipped:' || coalesce(o.parse_flags->>'snapshot_skipped', 'none')) as why,
                       count(*) as n, count(o.raw_snapshot) as with_snapshot,
                       coalesce(sum(octet_length(o.raw_snapshot)), 0) as bytes,
                       string_agg(distinct coalesce(o.http_status::text, 'null'), ',') as statuses
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.id > :after
                group by 1, 2, 3 order by 1, 2, 3
                """
            ),
            {"after": after},
        ).all()
        for r in rows:
            print(
                f"{r.slot:%m-%d %H:%M} {r.marketplace:9s} {r.why:22s} n={r.n:4d} "
                f"snap={r.with_snapshot:4d} bytes={r.bytes:9d} http={r.statuses}"
            )

        obs = c.execute(
            text(
                """
                select o.id, o.listing_id, l.marketplace, o.http_status, o.parse_status, o.parser_version,
                       o.extracted_price, o.extracted_availability, o.extracted_promo_badge,
                       o.parse_flags - 'cpor_activation' as flags
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.listing_id in (select listing_id from listing_observation where id > :after)
                  and o.http_status = 200 and o.parse_status = 'ok'
                order by o.listing_id, o.fetched_at, o.id
                """
            ),
            {"after": after},
        ).all()
        prev_by_listing: dict[int, object] = {}
        diffs: Counter = Counter()
        per_listing: dict[int, int] = defaultdict(int)
        examples: dict[str, tuple] = {}
        for o in obs:
            prev = prev_by_listing.get(o.listing_id)
            flags = o.flags or {}
            if o.id > after and flags.get("snapshot_stored") == "changed" and prev is not None:
                pf = prev.flags or {}
                keys = []
                if (prev.parser_version or "") != (o.parser_version or ""):
                    keys.append("parser_version")
                if _pk(prev.extracted_price) != _pk(o.extracted_price):
                    keys.append("price")
                if (prev.extracted_availability or None) != (o.extracted_availability or None):
                    keys.append("availability")
                if (prev.extracted_promo_badge or None) != (o.extracted_promo_badge or None):
                    keys.append("promo_badge")
                skip = {"snapshot_stored", "snapshot_skipped", "unchanged_since_observation_id", "status_transition",
                        "site_paused", "fetch_reason"}
                for k, v in flags.items():
                    if k in skip:
                        continue
                    if pf.get(k) != v:
                        keys.append("flag:" + k)
                label = "+".join(keys) or "(no compared difference vs stored prev)"
                diffs[(o.marketplace, label)] += 1
                per_listing[o.listing_id] += 1
                examples.setdefault(label, (o.listing_id, prev.id, o.id))
            prev_by_listing[o.listing_id] = o
        print("\n'changed' observations by marketplace and differing field(s):")
        for (mp, label), n in diffs.most_common():
            print(f"  {mp:9s} {n:4d}  {label}  e.g. listing/prev/obs {examples[label]}")
        flappers = sorted(per_listing.items(), key=lambda kv: -kv[1])[:10]
        print("listings with most 'changed' snapshots:", flappers)

        sizes = c.execute(
            text(
                """
                select l.marketplace, count(*) as n, round(avg(octet_length(o.raw_snapshot))) as avg_bytes
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.id > :after and o.raw_snapshot is not null and o.http_status = 200
                group by 1 order by 1
                """
            ),
            {"after": after},
        ).all()
        for s in sizes:
            print(f"avg snapshot (http 200) {s.marketplace:9s} n={s.n} avg_bytes={s.avg_bytes}")
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()

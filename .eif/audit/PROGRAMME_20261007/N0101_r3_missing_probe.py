"""N-0101 round 3: read-only. Which polled listing got no observation in the run with id > after_id?

Usage (from apps/api, PYTHONPATH=., venv python): N0101_r3_missing_probe.py <after_id> <prev_after_id>
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    after, prev_after = int(sys.argv[1]), int(sys.argv[2])
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        rows = c.execute(
            text(
                """
                select l.id, l.marketplace, l.status, l.product_id is not null as has_product,
                       l.meta_json ? 'consecutive_failures' as has_fail
                from customer_listing l
                where exists (select 1 from listing_observation o where o.listing_id = l.id and o.id > :prev and o.id <= :after)
                  and not exists (select 1 from listing_observation o where o.listing_id = l.id and o.id > :after)
                """
            ),
            {"after": after, "prev": prev_after},
        ).all()
        for r in rows:
            print("missing:", dict(r._mapping))
            obs = c.execute(
                text(
                    "select id, fetched_at, http_status, parse_status, extracted_price, extracted_availability, "
                    "extracted_promo_badge, parser_version, octet_length(raw_snapshot) as bytes, "
                    "parse_flags - 'cpor_activation' as flags "
                    "from listing_observation where listing_id = :lid order by id desc limit 3"
                ),
                {"lid": r.id},
            ).all()
            for o in obs:
                print("   ", dict(o._mapping))
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()

"""N-0101 round 3: read-only replay of record_observation for one listing on cip.

Feeds the listing's last stored snapshot back in as the "fetched" page (no network),
inside a READ ONLY transaction with autoflush off and flush disabled, then rolls back.
Shows whether the round 3 code path (previous-observation query, comparison, CPOR
activation) raises for that listing. Nothing is written.

Usage (from apps/api, PYTHONPATH=., venv python): N0101_r3_replay_probe.py <listing_id> <observation_id>
"""

from __future__ import annotations

import sys
import traceback

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.observation import decompress_snapshot
from app.services.listing_capture.registry import record_observation


def main() -> None:
    listing_id, obs_id = int(sys.argv[1]), int(sys.argv[2])
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", conn.execute(text("select current_database()")).scalar_one())
        session = Session(bind=conn, autoflush=False)
        session.flush = lambda *a, **k: None  # type: ignore[method-assign]
        try:
            listing = session.get(CustomerListing, listing_id)
            body = decompress_snapshot(session.get(ListingObservation, obs_id).raw_snapshot)
            print("listing", listing.id, listing.marketplace, listing.status, "body chars", len(body))
            obs = record_observation(session, listing, http_get=lambda _u: (200, body), consecutive_dead=0)
            flags = {k: v for k, v in (obs.parse_flags or {}).items() if k != "cpor_activation"}
            print("replay ok:", obs.parse_status, obs.extracted_price, obs.extracted_availability,
                  "snapshot", "kept" if obs.raw_snapshot else "skipped", flags)
            print("cpor_activation status:", (obs.parse_flags or {}).get("cpor_activation", {}).get("status"))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        finally:
            session.rollback()
            session.close()
        conn.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()

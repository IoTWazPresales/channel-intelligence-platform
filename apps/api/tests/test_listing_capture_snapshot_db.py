"""N-0101 round 3: snapshot policy and retention against Postgres, cip_test only.

Inserts a fixture listing and observations inside one transaction that is always rolled
back. Skips on any database other than cip_test (it never writes to cip). Run with
DATABASE_URL_SYNC pointed at cip_test (see .eif/audit/PROGRAMME_20261007/N0101_r3_run_db_tests.py).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.marketplace_vocab import PARSER_VERSION
from app.services.listing_capture.observation import compress_snapshot
from app.services.listing_capture.registry import record_observation, reparse_observation
from app.services.listing_capture.snapshot_retention import clear_expired_snapshots


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"snapshot DB test runs on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
        eng.dispose()


def _fixture_listing(session: Session) -> CustomerListing:
    customer_id = session.execute(text("select min(id) from dim_customer")).scalar_one()
    if customer_id is None:
        pytest.skip("cip_test has no dim_customer row")
    listing = CustomerListing(
        customer_id=int(customer_id),
        url=f"https://example.test/n0101-r3/{uuid.uuid4().hex}",
        marketplace="evetech",
        status="active",
        source="manual",
    )
    session.add(listing)
    session.flush()
    return listing


def _page(price: float) -> str:
    return json.dumps({"price": price, "availability": "in_stock"})


def _row(session: Session, obs_id: int):
    return session.execute(
        text(
            "select id, raw_snapshot, extracted_price, extracted_availability, parse_flags "
            "from listing_observation where id = :id"
        ),
        {"id": obs_id},
    ).one()


def test_record_observation_unchanged_stores_no_snapshot_in_postgres(db_session: Session) -> None:
    listing = _fixture_listing(db_session)
    first = record_observation(db_session, listing, http_get=lambda _u: (200, _page(999.0)))
    second = record_observation(db_session, listing, http_get=lambda _u: (200, _page(999.0)))
    changed = record_observation(db_session, listing, http_get=lambda _u: (200, _page(949.0)))
    failed = record_observation(db_session, listing, http_get=lambda _u: (200, "<html>no price</html>"))
    db_session.flush()

    r1, r2, r3, r4 = (_row(db_session, o.id) for o in (first, second, changed, failed))
    assert r1.raw_snapshot is not None and r1.parse_flags["snapshot_stored"] == "first_observation"
    assert r2.raw_snapshot is None
    assert r2.parse_flags["snapshot_skipped"] == "unchanged"
    assert r2.parse_flags["unchanged_since_observation_id"] == first.id
    assert float(r2.extracted_price) == 999.0 and r2.extracted_availability == "in_stock"
    assert r3.raw_snapshot is not None and r3.parse_flags["snapshot_stored"] == "changed"
    assert r4.raw_snapshot is not None and r4.parse_flags["snapshot_stored"] == "parse_failed"

    # Re-parse of the payload-less row is a no-op, not a failure.
    reparse_observation(db_session, second, marketplace="evetech")
    db_session.flush()
    again = _row(db_session, second.id)
    assert float(again.extracted_price) == 999.0
    assert "reparsed" not in again.parse_flags


def test_retention_clears_only_payloads_older_than_90_days_and_keeps_rows(db_session: Session) -> None:
    listing = _fixture_listing(db_session)
    now = datetime.now(timezone.utc)
    blob = compress_snapshot("<html>R 1 299</html>")

    def obs(days_ago: float, snapshot: bool, flags=None) -> ListingObservation:
        o = ListingObservation(
            listing_id=listing.id,
            fetched_at=now - timedelta(days=days_ago),
            http_status=200,
            raw_snapshot=blob if snapshot else None,
            parser_version=PARSER_VERSION,
            extracted_price=1299,
            extracted_availability="unknown",
            parse_status="ok",
            parse_flags=flags,
        )
        db_session.add(o)
        return o

    old_a = obs(100, True, {"method": "html_zar"})
    old_b = obs(90.5, True, None)
    old_empty = obs(120, False, {"snapshot_skipped": "unchanged"})
    recent = obs(89.5, True, {"method": "html_zar"})
    today = obs(0, True, None)
    db_session.flush()
    total_before = db_session.execute(text("select count(*) from listing_observation")).scalar_one()

    result = clear_expired_snapshots(db_session, now=now, batch_size=1, commit=False)

    assert result["rows_deleted"] == 0
    assert result["snapshots_cleared"] >= 2
    assert result["bytes_cleared"] >= 2 * len(blob)
    assert db_session.execute(text("select count(*) from listing_observation")).scalar_one() == total_before
    for o in (old_a, old_b):
        r = _row(db_session, o.id)
        assert r.raw_snapshot is None
        assert float(r.extracted_price) == 1299.0  # extracted fields kept
        assert r.parse_flags["snapshot_cleared"]["reason"] == "retention"
        assert r.parse_flags["snapshot_cleared"]["retention_days"] == 90
    assert _row(db_session, old_a.id).parse_flags["method"] == "html_zar"  # existing flags merged
    r_empty = _row(db_session, old_empty.id)
    assert r_empty.raw_snapshot is None and "snapshot_cleared" not in r_empty.parse_flags
    for o in (recent, today):
        r = _row(db_session, o.id)
        assert bytes(r.raw_snapshot) == blob
        assert "snapshot_cleared" not in (r.parse_flags or {})

    # Idempotent: nothing left to clear for these rows.
    second = clear_expired_snapshots(db_session, now=now, commit=False)
    assert second["snapshots_cleared"] == 0

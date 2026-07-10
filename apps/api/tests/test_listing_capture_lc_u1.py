"""LC-U1 Listing Capture unit tests (no DB / mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.listing_capture.observation import (
    compress_snapshot,
    decompress_snapshot,
    parse_snapshot_text,
    should_backoff_dead_link,
)
from app.services.listing_capture.registry import (
    confirm_proposal,
    create_listing,
    import_listings_csv,
    record_observation,
    reparse_observation,
    scheduler_should_run,
    set_listing_status,
)
from app.services.listing_capture.marketplace_vocab import LISTING_MARKETPLACE_SET


def test_marketplace_vocab() -> None:
    assert "takealot" in LISTING_MARKETPLACE_SET
    assert "evetech" in LISTING_MARKETPLACE_SET


def test_compress_roundtrip() -> None:
    blob = compress_snapshot('{"price": 99.5}')
    assert decompress_snapshot(blob) == '{"price": 99.5}'


def test_parse_json_and_failure() -> None:
    ok = parse_snapshot_text('{"price": 120.0, "availability": "in_stock"}', marketplace="takealot")
    assert ok.parse_status == "ok" and ok.price == 120.0
    bad = parse_snapshot_text("no price here", marketplace="takealot")
    assert bad.parse_status == "parse_failed"


def test_dead_link_backoff() -> None:
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    assert should_backoff_dead_link(consecutive_dead=3, last_fetch_at=now - timedelta(hours=1), now=now)
    assert not should_backoff_dead_link(consecutive_dead=1, last_fetch_at=now, now=now)


def test_create_and_status(monkeypatch) -> None:
    session = MagicMock()
    listing = create_listing(
        session,
        customer_id=1,
        url="https://www.takealot.com/x/PLID1",
        marketplace="takealot",
        product_id=10,
        source="manual",
    )
    assert listing.marketplace == "takealot"
    set_listing_status(session, listing, status="out_of_stock")
    assert listing.status == "out_of_stock"


def test_csv_flag_not_block() -> None:
    session = MagicMock()
    csv_text = "customer_id,url,marketplace,product_id\n1,https://t.com/a,takealot,5\nbad,url,takealot,\n"
    # create_listing will be called; MagicMock session is fine
    out = import_listings_csv(session, csv_text=csv_text)
    assert out["ok"] is True
    assert out["created"] >= 1
    assert len(out["row_flags"]) >= 1


def test_confirm_proposal_never_auto() -> None:
    session = MagicMock()
    seed = SimpleNamespace(
        id=7,
        customer_id=1,
        marketplace="takealot",
        external_id="TSIN-1",
        product_id=9,
        status="proposed",
    )
    session.get.return_value = seed
    listing = confirm_proposal(session, seed_id=7, url="https://www.takealot.com/p/TSIN-1")
    assert listing.source == "feed_proposal"
    assert seed.status == "confirmed"


def test_record_observation_mocked_http() -> None:
    session = MagicMock()
    listing = SimpleNamespace(
        id=1,
        url="https://example.com/p",
        marketplace="takealot",
        status="active",
        status_observed_at=None,
    )

    def http_get(_url: str):
        return 200, '{"price": 55.0, "availability": "in_stock"}'

    obs = record_observation(session, listing, http_get=http_get)
    assert obs.http_status == 200
    assert obs.parse_status == "ok"
    assert float(obs.extracted_price) == 55.0
    assert obs.raw_snapshot is not None


def test_reparse_without_refetch() -> None:
    session = MagicMock()
    blob = compress_snapshot('{"price": 10}')
    obs = SimpleNamespace(
        raw_snapshot=blob,
        parser_version="old",
        extracted_price=None,
        extracted_availability=None,
        extracted_promo_badge=None,
        parse_status="parse_failed",
        parse_flags={},
    )
    reparse_observation(session, obs, marketplace="takealot")
    assert obs.parse_status == "ok"
    assert float(obs.extracted_price) == 10.0
    assert obs.parse_flags.get("reparsed") is True


def test_scheduler_gate() -> None:
    session = MagicMock()
    session.scalar.return_value = 0
    g = scheduler_should_run(session, schedule_enabled=True)
    assert g["should_run"] is False
    session.scalar.return_value = 3
    g2 = scheduler_should_run(session, schedule_enabled=False)
    assert g2["should_run"] is False
    g3 = scheduler_should_run(session, schedule_enabled=True)
    assert g3["should_run"] is True

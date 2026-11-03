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
import pytest

from app.services.listing_capture import marketplace_vocab, registry
from tests.listing_site_fixtures import html_site


@pytest.fixture
def known_sites(monkeypatch):
    """The tenant has site ``shop-a``; any other key is unknown."""
    sites = {"shop-a": html_site("shop-a")}
    monkeypatch.setattr(registry, "site_for_customer", lambda _s, _cid, key: sites.get((key or "").strip().lower()))
    return sites


def test_sites_are_not_a_code_list() -> None:
    assert not hasattr(marketplace_vocab, "LISTING_MARKETPLACES")
    assert not hasattr(marketplace_vocab, "LISTING_MARKETPLACE_SET")


def test_compress_roundtrip() -> None:
    blob = compress_snapshot('{"price": 99.5}')
    assert decompress_snapshot(blob) == '{"price": 99.5}'


def test_parse_json_and_failure() -> None:
    ok = parse_snapshot_text('{"price": 120.0, "availability": "in_stock"}', marketplace="shop-a")
    assert ok.parse_status == "ok" and ok.price == 120.0
    bad = parse_snapshot_text("no price here", marketplace="shop-a")
    assert bad.parse_status == "parse_failed"


def test_dead_link_backoff() -> None:
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    assert should_backoff_dead_link(consecutive_dead=3, last_fetch_at=now - timedelta(hours=1), now=now)
    assert not should_backoff_dead_link(consecutive_dead=1, last_fetch_at=now, now=now)


def test_create_and_status(known_sites) -> None:
    session = MagicMock()
    listing = create_listing(
        session,
        customer_id=1,
        url="https://shop-a.example.test/p/1",
        marketplace="Shop-A",
        product_id=10,
        source="manual",
    )
    assert listing.marketplace == "shop-a"
    set_listing_status(session, listing, status="out_of_stock")
    assert listing.status == "out_of_stock"


def test_create_listing_rejects_a_site_the_tenant_does_not_have(known_sites) -> None:
    with pytest.raises(ValueError, match="unknown site"):
        create_listing(MagicMock(), customer_id=1, url="https://x.example.test/p", marketplace="shop-z")


def test_create_listing_rejects_an_inactive_site(monkeypatch) -> None:
    from dataclasses import replace

    inactive = replace(html_site("shop-a"), is_active=False)
    monkeypatch.setattr(registry, "site_for_customer", lambda *_a: inactive)
    with pytest.raises(ValueError, match="inactive"):
        create_listing(MagicMock(), customer_id=1, url="https://shop-a.example.test/p", marketplace="shop-a")


def test_csv_flag_not_block(known_sites) -> None:
    session = MagicMock()
    csv_text = (
        "customer_id,url,marketplace,product_id\n"
        "1,https://shop-a.example.test/a,shop-a,5\n"
        "bad,url,shop-a,\n"
        "1,https://shop-z.example.test/a,shop-z,5\n"
    )
    out = import_listings_csv(session, csv_text=csv_text)
    assert out["ok"] is True
    assert out["created"] == 1
    assert [f["row"] for f in out["row_flags"]] == [2, 3]
    assert "unknown site" in out["row_flags"][1]["error"]


def test_confirm_proposal_never_auto(known_sites) -> None:
    session = MagicMock()
    seed = SimpleNamespace(
        id=7,
        customer_id=1,
        marketplace="shop-a",
        external_id="SKU-1",
        product_id=9,
        status="proposed",
    )
    session.get.return_value = seed
    listing = confirm_proposal(session, seed_id=7, url="https://shop-a.example.test/p/SKU-1")
    assert listing.source == "feed_proposal"
    assert seed.status == "confirmed"


def test_record_observation_mocked_http() -> None:
    session = MagicMock()
    listing = SimpleNamespace(
        id=1,
        url="https://example.com/p",
        marketplace="shop-a",
        status="active",
        status_observed_at=None,
    )

    def http_get(_url: str):
        return 200, '{"price": 55.0, "availability": "in_stock"}'

    obs = record_observation(session, listing, http_get=http_get, site=html_site("shop-a"))
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
    reparse_observation(session, obs)
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

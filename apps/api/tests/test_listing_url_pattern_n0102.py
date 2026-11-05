"""N-0102: product URL patterns come from confirmed listing URLs.

Confirmed listing_link rows win. When a marketplace has none, the source is
customer_listing rows stamped with url_verified_at. The read is database cip.
Pattern writes run only on cip_test and roll back.
"""

from __future__ import annotations

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.listing_site import ListingSite
from app.services.listing_capture import url_pattern as url_pattern_module
from app.services.listing_capture.url_pattern import (
    NO_PATTERN,
    PATTERN_ACTOR,
    WRITE_DATABASE,
    derive_listing_url_pattern,
    page_for_external_id,
    write_listing_url_pattern,
)

MARKETS = ("amazon", "evetech", "takealot")
PROOF_MARKET = "evetech"
PROOF_COUNT = 63
_SLASH = chr(47)


def _url_for(database: str) -> str:
    sync = get_settings().database_url_sync
    for scheme in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if sync.startswith(scheme):
            sync = "postgresql://" + sync[len(scheme) :]
            break
    base, _, leaf = sync.rpartition(_SLASH)
    if not base:
        raise RuntimeError("database url has no database name")
    query = ""
    if "?" in leaf:
        query = "?" + leaf.split("?", 1)[1]
    return base + _SLASH + database + query


def _load_confirmed() -> tuple[dict[str, tuple[str, list[str]]], list[str]]:
    print("module=" + url_pattern_module.__file__)
    with psycopg.connect(_url_for("cip"), options="-c default_transaction_read_only=on") as conn:
        database = conn.execute("select current_database()").fetchone()[0]
        print("current_database()=" + str(database))
        assert database == "cip"
        link_sql = (
            "select s.site_key, l.url "
            "from listing_link l "
            "join listing_site s on s.id = l.site_id "
            "where l.status = %s and s.site_key = any(%s) "
            "order by s.site_key, l.id"
        )
        links = conn.execute(link_sql, ("confirmed", list(MARKETS))).fetchall()
        verified_sql = (
            "select marketplace, url "
            "from customer_listing "
            "where marketplace = any(%s) "
            "and meta_json ? %s "
            "and url is not null "
            "and btrim(url) <> %s "
            "order by marketplace, id"
        )
        verified = conn.execute(verified_sql, (list(MARKETS), "url_verified_at", "")).fetchall()
        seed_sql = (
            "select external_id from cst_listing_seed "
            "where marketplace = %s and status = %s "
            "order by id"
        )
        seeds = [row[0] for row in conn.execute(seed_sql, (PROOF_MARKET, "proposed")).fetchall()]
    sources: dict[str, tuple[str, list[str]]] = {}
    for market in MARKETS:
        market_links = [url for key, url in links if key == market]
        if market_links:
            sources[market] = ("listing_link", market_links)
        else:
            sources[market] = (
                "url_verified_at",
                [url for name, url in verified if name == market],
            )
        print(market + " source=" + sources[market][0] + " n=" + str(len(sources[market][1])))
    return sources, seeds


def test_confirmed_urls_and_evetech_seeds() -> None:
    sources, seeds = _load_confirmed()
    patterns = {}
    for market in MARKETS:
        source, urls = sources[market]
        assert urls, market + " has no confirmed URLs"
        derived = derive_listing_url_pattern(urls)
        assert derived is not None, market + " " + NO_PATTERN + " n=" + str(len(urls))
        assert all(derived.reproduces(url) for url in urls)
        assert derived.page_id(urls[0])
        patterns[market] = derived
        print(market + " product_url_pattern=" + derived.product_url_pattern)
        print(market + " page_id_pattern=" + derived.page_id_pattern)
        print(market + " sample=" + urls[0])
        print(market + " source_used=" + source)
    assert len(seeds) == PROOF_COUNT
    outcomes = [page_for_external_id(patterns[PROOF_MARKET], external_id) for external_id in seeds]
    pages = [item for item in outcomes if item != NO_PATTERN]
    phrases = [item for item in outcomes if item == NO_PATTERN]
    for external_id, outcome in zip(seeds, outcomes):
        if outcome == NO_PATTERN:
            continue
        assert patterns[PROOF_MARKET].page_id(outcome) == external_id
    assert len(pages) + len(phrases) == PROOF_COUNT
    assert pages == []
    assert len(phrases) == PROOF_COUNT
    print(
        PROOF_MARKET
        + " proposed="
        + str(len(seeds))
        + " pages="
        + str(len(pages))
        + " phrase="
        + str(len(phrases))
    )


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        database = conn.execute(text("select current_database()")).scalar()
        print("write_current_database()=" + str(database))
        if database != WRITE_DATABASE:
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _proof_row(db: Session, site_key: str) -> ListingSite:
    row = ListingSite(
        tenant_id="default",
        site_key=site_key,
        display_name="N0102 pattern proof",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_write_pattern_on_cip_test_rolls_back(session: Session) -> None:
    sources, _seeds = _load_confirmed()
    urls = sources[PROOF_MARKET][1]
    row = _proof_row(session, "n0102pat")
    result = write_listing_url_pattern(session, row, urls)
    assert result["written"] is True
    assert result["database"] == WRITE_DATABASE
    assert row.product_url_pattern == result["product_url_pattern"]
    assert row.page_id_pattern == result["page_id_pattern"]
    assert row.adapter_key is None
    assert row.updated_by == PATTERN_ACTOR
    print("cip_test product_url_pattern=" + str(row.product_url_pattern))
    print("cip_test page_id_pattern=" + str(row.page_id_pattern))


def _sample_url(host: str, *segments: str) -> str:
    return "https" + chr(58) + _SLASH + _SLASH + host + _SLASH + _SLASH.join(segments)


def test_mismatch_does_not_write(session: Session) -> None:
    row = _proof_row(session, "n0102miss")
    urls = [
        _sample_url("one.example.test", "dp", "111"),
        _sample_url("two.example.test", "dp", "222"),
    ]
    result = write_listing_url_pattern(session, row, urls)
    assert result["written"] is False
    assert result["reason"] == NO_PATTERN
    assert result["database"] == WRITE_DATABASE
    assert row.product_url_pattern is None
    assert row.page_id_pattern is None


class _CipDatabase:
    def scalar(self):
        return "cip"


class _CipSession:
    def execute(self, statement):
        del statement
        return _CipDatabase()


def test_refuses_database_named_cip() -> None:
    result = write_listing_url_pattern(_CipSession(), None, [])
    assert result["written"] is False
    assert result["database"] == "cip"
    assert result["reason"] == "refusing write on cip"
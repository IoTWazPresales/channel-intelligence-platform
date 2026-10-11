"""N-0101 round 3: snapshot policy (Warren, 2026-10-08) and snapshot retention.

A raw page snapshot is stored only on the first observation, when the fetch or parse
failed, when the extracted fields changed versus the listing's previous successful
observation, or on a status transition. Snapshots older than 90 days are cleared
(payload only). Re-parse skips an observation without a payload.

No DB and no network: an in-memory session that answers the "previous successful
observation" query from the observations added to it. The SQL of the retention job is
proven on cip_test in ``test_listing_capture_snapshot_db.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.models.listing_capture import ListingObservation
from app.services.listing_capture.marketplace_vocab import PARSER_VERSION
from app.services.listing_capture.observation import compress_snapshot
from app.services.listing_capture.registry import (
    SNAPSHOT_SKIPPED_UNCHANGED,
    previous_successful_observation,
    record_observation,
    reparse_observation,
)
from app.services.listing_capture.snapshot_retention import clear_expired_snapshots


def _page(price: float = 999.0, availability: str = "in_stock", promo: str | None = None) -> str:
    body = {"price": price, "availability": availability}
    if promo:
        body["promo_badge"] = promo
    return json.dumps(body)


class MemorySession:
    """Holds added observations; ``scalars(stmt).first()`` returns the latest one that is
    HTTP 200 + parse ok for the listing (what the real query selects). An observation is
    visible to the query as soon as it is added (like autoflush)."""

    def __init__(self) -> None:
        self.observations: list[ListingObservation] = []
        self.statements: list = []
        self._next_id = 1

    def add(self, obj) -> None:
        if isinstance(obj, ListingObservation) and obj not in self.observations:
            obj.id = self._next_id
            self._next_id += 1
            self.observations.append(obj)

    def flush(self) -> None:
        return None

    def get(self, _model, _id):
        return None

    def execute(self, *_a, **_k):
        return MagicMock()

    def scalar(self, *_a, **_k):
        return None

    def scalars(self, stmt):
        self.statements.append(stmt)
        ok = [o for o in self.observations if o.http_status == 200 and o.parse_status == "ok"]
        result = MagicMock()
        result.first.return_value = ok[-1] if ok else None
        result.all.return_value = ok
        return result


def _listing(lid: int = 7, marketplace: str = "evetech", status: str = "active", **kw):
    return SimpleNamespace(
        id=lid,
        url=kw.pop("url", f"https://example.test/{marketplace}/{lid}"),
        marketplace=marketplace,
        status=status,
        status_observed_at=None,
        meta_json=kw.pop("meta_json", None),
        product_id=None,
        external_id=kw.pop("external_id", None),
    )


def _observe(session, listing, status: int, body: str):
    return record_observation(session, listing, http_get=lambda _u: (status, body))


# ---------------------------------------------------------------- store / skip


def test_first_observation_stores_snapshot() -> None:
    session = MemorySession()
    obs = _observe(session, _listing(), 200, _page())
    assert obs.raw_snapshot is not None
    assert obs.parse_flags["snapshot_stored"] == "first_observation"
    assert "snapshot_skipped" not in obs.parse_flags


def test_unchanged_observation_stores_no_snapshot_but_keeps_fields() -> None:
    session = MemorySession()
    listing = _listing()
    first = _observe(session, listing, 200, _page(promo="10% off"))
    second = _observe(session, listing, 200, _page(promo="10% off"))
    assert first.raw_snapshot is not None
    assert second.raw_snapshot is None
    assert second.parse_flags["snapshot_skipped"] == SNAPSHOT_SKIPPED_UNCHANGED
    assert second.parse_flags["unchanged_since_observation_id"] == first.id
    # The observation row and its extracted fields are still written.
    assert second in session.observations
    assert second.http_status == 200 and second.parse_status == "ok"
    assert float(second.extracted_price) == 999.0
    assert second.extracted_availability == "in_stock"
    assert second.extracted_promo_badge == "10% off"
    assert second.parser_version == PARSER_VERSION


def test_changed_price_stores_snapshot() -> None:
    session = MemorySession()
    listing = _listing()
    _observe(session, listing, 200, _page(price=999.0))
    obs = _observe(session, listing, 200, _page(price=949.0))
    assert obs.raw_snapshot is not None
    assert obs.parse_flags["snapshot_stored"] == "changed"
    assert "snapshot_skipped" not in obs.parse_flags


def test_changed_availability_or_promo_stores_snapshot() -> None:
    session = MemorySession()
    listing = _listing()
    _observe(session, listing, 200, _page())
    promo = _observe(session, listing, 200, _page(promo="Save R50"))
    assert promo.raw_snapshot is not None and promo.parse_flags["snapshot_stored"] == "changed"
    unknown = _observe(session, listing, 200, _page(availability="unknown", promo="Save R50"))
    assert unknown.raw_snapshot is not None and unknown.parse_flags["snapshot_stored"] == "changed"
    same = _observe(session, listing, 200, _page(availability="unknown", promo="Save R50"))
    assert same.raw_snapshot is None


def test_failed_parse_stores_snapshot_and_next_ok_compares_with_last_success() -> None:
    session = MemorySession()
    listing = _listing()
    first = _observe(session, listing, 200, _page())
    failed = _observe(session, listing, 200, "<html>captcha, no price here</html>")
    assert failed.parse_status == "parse_failed"
    assert failed.raw_snapshot is not None
    assert failed.parse_flags["snapshot_stored"] == "parse_failed"
    # Back to the same page: compared with the previous SUCCESSFUL observation (first).
    again = _observe(session, listing, 200, _page())
    assert again.raw_snapshot is None
    assert again.parse_flags["unchanged_since_observation_id"] == first.id


def test_failed_fetch_stores_snapshot_even_when_fields_match() -> None:
    session = MemorySession()
    listing = _listing()
    _observe(session, listing, 200, _page())
    # A non-200 page that still parses to the same fields is a failed fetch: keep it.
    obs = _observe(session, listing, 500, _page())
    assert obs.parse_status == "ok"
    assert obs.raw_snapshot is not None
    assert obs.parse_flags["snapshot_stored"] == "fetch_failed"
    gone = _observe(session, listing, 404, "")
    assert gone.raw_snapshot is not None
    assert gone.parse_flags["snapshot_stored"] == "fetch_failed"


def test_parser_version_change_stores_snapshot() -> None:
    session = MemorySession()
    listing = _listing()
    first = _observe(session, listing, 200, _page())
    first.parser_version = "lc-v0.1"
    first.parse_flags = {**first.parse_flags, "parser_version": "lc-v0.1"}
    obs = _observe(session, listing, 200, _page())
    assert obs.raw_snapshot is not None
    assert obs.parse_flags["snapshot_stored"] == "changed"


def test_db_decimal_price_equals_float_parse() -> None:
    """A previous row read back from Postgres has a Decimal price (Numeric(18, 4))."""
    session = MemorySession()
    listing = _listing()
    first = _observe(session, listing, 200, _page(price=1799.5))
    first.extracted_price = Decimal("1799.5000")
    obs = _observe(session, listing, 200, _page(price=1799.5))
    assert obs.raw_snapshot is None


def test_status_transition_keeps_snapshot_even_when_fields_match() -> None:
    session = MemorySession()
    listing = _listing()
    _observe(session, listing, 200, _page())
    listing.status = "dead_link"  # e.g. a 404 run in between
    obs = _observe(session, listing, 200, _page())
    assert listing.status == "active"
    assert obs.parse_flags["status_transition"]["reason"] == "link_recovered"
    assert obs.raw_snapshot is not None
    assert obs.parse_flags["snapshot_stored"] == "status_transition"


def _tkl_details(*, price: float = 1799, sku: int = 222547542) -> str:
    return json.dumps(
        {
            "desktop_href": "https://www.takealot.com/x/PLID98174082",
            "buybox": {
                "plid": 98174082,
                "tsin": 99510999,
                "items": [
                    {
                        "is_selected": True,
                        "is_add_to_cart_available": True,
                        "sku": sku,
                        "price": price,
                        "listing_price": 2699,
                        "stock_availability": {"status": "In stock"},
                    }
                ],
            },
            "badges": {"items": [{"type": "saving", "value": "33% off"}]},
        }
    )


def test_takealot_parser_flag_change_counts_as_changed() -> None:
    """Any field the parser extracts (here the buybox SKU) counts, not only price."""
    session = MemorySession()
    listing = _listing(9, marketplace="takealot", url="https://www.takealot.com/x/PLID98174082")
    first = _observe(session, listing, 200, _tkl_details())
    same = _observe(session, listing, 200, _tkl_details())
    other_seller = _observe(session, listing, 200, _tkl_details(sku=111))
    assert first.raw_snapshot is not None
    assert same.raw_snapshot is None and same.parse_flags["snapshot_skipped"] == "unchanged"
    assert other_seller.raw_snapshot is not None
    assert other_seller.parse_flags["snapshot_stored"] == "changed"


def test_mocked_session_without_previous_keeps_snapshot() -> None:
    obs = record_observation(MagicMock(), _listing(), http_get=lambda _u: (200, _page()))
    assert obs.raw_snapshot is not None


def test_previous_successful_query_shape() -> None:
    session = MemorySession()
    previous_successful_observation(session, 42)
    sql = str(session.statements[-1].compile(dialect=postgresql.dialect()))
    assert "listing_observation.listing_id = " in sql
    assert "listing_observation.http_status = " in sql
    assert "listing_observation.parse_status = " in sql
    assert "ORDER BY listing_observation.fetched_at DESC, listing_observation.id DESC" in sql
    assert "LIMIT" in sql
    # The payload is not loaded to compare fields.
    assert "raw_snapshot" not in sql
    assert previous_successful_observation(session, None) is None


# ---------------------------------------------------------------- re-parse


def test_reparse_skips_observation_without_snapshot() -> None:
    session = MagicMock()
    obs = SimpleNamespace(
        id=5,
        listing_id=7,
        raw_snapshot=None,
        parser_version=PARSER_VERSION,
        extracted_price=Decimal("999.0000"),
        extracted_availability="in_stock",
        extracted_promo_badge=None,
        parse_status="ok",
        parse_flags={"snapshot_skipped": "unchanged"},
    )
    out = reparse_observation(session, obs, marketplace="evetech")
    assert out is obs
    assert obs.parse_status == "ok"
    assert obs.extracted_price == Decimal("999.0000")
    assert obs.extracted_availability == "in_stock"
    assert obs.parse_flags == {"snapshot_skipped": "unchanged"}
    session.add.assert_not_called()
    cleared = SimpleNamespace(**{**obs.__dict__, "raw_snapshot": b"", "parse_flags": {"snapshot_cleared": {}}})
    assert reparse_observation(session, cleared, marketplace="evetech").parse_status == "ok"


def test_reparse_with_snapshot_still_reparses() -> None:
    obs = SimpleNamespace(
        raw_snapshot=compress_snapshot('{"price": 10}'),
        parser_version="old",
        extracted_price=None,
        extracted_availability=None,
        extracted_promo_badge=None,
        parse_status="parse_failed",
        parse_flags={},
    )
    reparse_observation(MagicMock(), obs, marketplace="evetech")
    assert obs.parse_status == "ok" and float(obs.extracted_price) == 10.0


# ---------------------------------------------------------------- retention loop (SQL on cip_test)


class _RetentionSession:
    """Serves the keyset select from a list of (id, bytes) rows; counts updates/commits."""

    def __init__(self, rows: list[tuple[int, int]]) -> None:
        self.rows = rows
        self.updated: list[int] = []
        self.commits = 0
        self.selects: list[dict] = []

    def execute(self, stmt, params):
        sql = str(stmt)
        if sql.lstrip().upper().startswith("SELECT"):
            self.selects.append(dict(params))
            after = params["after_id"]
            out = [SimpleNamespace(id=i, bytes=b) for i, b in self.rows if i > after and i not in self.updated]
            res = MagicMock()
            res.all.return_value = out[: params["batch_size"]]
            return res
        assert "DELETE" not in sql.upper()
        self.updated.extend(params["ids"])
        res = MagicMock()
        res.rowcount = len(params["ids"])
        return res

    def commit(self) -> None:
        self.commits += 1


def test_retention_batches_by_keyset_commits_each_and_never_deletes() -> None:
    session = _RetentionSession([(i, 100) for i in range(1, 12)])
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    result = clear_expired_snapshots(session, now=now, batch_size=5)
    assert result["snapshots_cleared"] == 11
    assert result["bytes_cleared"] == 1100
    assert result["batches"] == 3
    assert result["rows_deleted"] == 0
    assert session.commits == 3
    assert [s["after_id"] for s in session.selects] == [0, 5, 10]
    assert session.selects[0]["cutoff"] == now - timedelta(days=90)


def test_retention_stops_at_time_limit() -> None:
    session = _RetentionSession([(i, 1) for i in range(1, 100)])
    # start, check before batch 1, check before batch 2, check before batch 3 (over), duration
    ticks = iter([0.0, 0.0, 1.0, 999.0, 999.0])
    result = clear_expired_snapshots(
        session, batch_size=10, time_limit_seconds=100, clock=lambda: next(ticks)
    )
    assert result["stopped_reason"] == "time_limit"
    assert result["batches"] == 2
    assert result["snapshots_cleared"] == 20


def test_retention_beat_entry_daily() -> None:
    from celery.schedules import crontab

    from app.worker.celery_app import build_beat_schedule, celery_app

    entry = build_beat_schedule()["listing-capture-snapshot-retention"]
    assert entry["task"] == "listing_capture.clear_expired_snapshots"
    assert entry["schedule"] == crontab(hour=3, minute=15)
    assert "listing_capture.clear_expired_snapshots" in celery_app.tasks

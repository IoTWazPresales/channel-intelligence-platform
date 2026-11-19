"""Listings list returns real totals and per-status counts over every matching row (BACKLOG-226).

The page used to be cut from a fully loaded list and the screen counted that page. Counts are now
SQL aggregates over all rows matching the filters. No DB: a recording session.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.api.v1.endpoints import listing_capture as ep
from sqlalchemy.dialects import postgresql


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class Recorder:
    def __init__(self, *, total: int, by_status: dict[str, int], unlinked: int) -> None:
        self.total, self.by_status, self.unlinked = total, by_status, unlinked
        self.sql: list[str] = []

    def execute(self, stmt: Any) -> list[Any]:
        text = _sql(stmt)
        self.sql.append(text)
        if "GROUP BY" in text:
            return [SimpleNamespace(status=k, n=v) for k, v in self.by_status.items()]
        return [SimpleNamespace(total=self.total, unlinked=self.unlinked)]


def test_counts_cover_all_rows_in_two_statements() -> None:
    rec = Recorder(
        total=218, by_status={"active": 107, "out_of_stock": 69, "dead_link": 42}, unlinked=5
    )
    total, status_counts, unlinked = ep.listing_counts(
        rec, customer_id=None, marketplace=None, status=None
    )  # type: ignore[arg-type]
    assert total == 218 and unlinked == 5
    assert status_counts == {"active": 107, "out_of_stock": 69, "dead_link": 42}
    assert len(rec.sql) == 2
    for text in rec.sql:
        assert "LIMIT" not in text.upper() and "OFFSET" not in text.upper()


def test_total_follows_every_filter_but_status_counts_ignore_the_status_filter() -> None:
    rec = Recorder(total=107, by_status={"active": 107, "dead_link": 3}, unlinked=0)
    ep.listing_counts(rec, customer_id=9, marketplace=" Shop-A ", status="active")  # type: ignore[arg-type]
    total_sql, by_status_sql = rec.sql
    assert "customer_listing.customer_id = 9" in total_sql
    assert "customer_listing.marketplace = 'shop-a'" in total_sql
    assert "customer_listing.status = 'active'" in total_sql
    # The breakdown stays a breakdown: filtering to one status must not hide the others.
    assert "customer_listing.customer_id = 9" in by_status_sql
    assert "customer_listing.marketplace = 'shop-a'" in by_status_sql
    assert "customer_listing.status =" not in by_status_sql


def test_no_rows_gives_zeroes() -> None:
    rec = Recorder(total=0, by_status={}, unlinked=0)
    assert ep.listing_counts(rec, customer_id=None, marketplace=None, status=None) == (0, {}, 0)  # type: ignore[arg-type]

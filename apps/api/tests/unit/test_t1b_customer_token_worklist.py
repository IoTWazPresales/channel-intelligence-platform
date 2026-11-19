"""T1b: the customer-token worklist bounds its reads and its per-token work.

Before: every unresolved line (all columns, JSON payloads included) and every line of every case it
touches was loaded as a full ORM row; every token scanned every shipment row (tokens x shipments);
and the distributor-confirmer preview ran for up to 500 tokens although the page shows ``limit``.
Now: column reads only, the isolation preload is narrowed in SQL to the rows isolation can use, the
shipment rows are indexed by PO once, and offers and labels are built only for the returned page.
The output for the same ``limit`` is unchanged (counts and totals still cover every token).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.services.commercial_planner import lineup_customer_token_stamp as mod

OC = 900


def _line(id, case_id, token, product_id, customer_id=None):
    return SimpleNamespace(id=id, case_id=case_id, customer_token=token, product_id=product_id, customer_id=customer_id)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _Db:
    """Answers each statement by the table it reads; records the SQL text."""

    def __init__(self, *, unresolved, isolation, case_pos, customers):
        self.unresolved = unresolved
        self.isolation = isolation
        self.case_pos = case_pos
        self.customers = customers
        self.sql: list[str] = []

    async def execute(self, stmt):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.sql.append(sql)
        if "FROM commercial_lineup_case_po" in sql:
            return _Result(self.case_pos)
        if "FROM dim_customer" in sql:
            return _Result(self.customers)
        if "FROM commercial_lineup_line" in sql and "commercial_lineup_line.customer_id IS NULL" in sql:
            return _Result(self.unresolved)
        if "FROM commercial_lineup_line" in sql:
            return _Result(self.isolation)
        raise AssertionError(f"unexpected statement: {sql}")


class _CountingList(list):
    iterations = 0

    def __iter__(self):
        type(self).iterations += 1
        return super().__iter__()


def _world(extra_tokens: int = 0):
    unresolved = [
        _line(1, 1, "Tok-A", 5),
        _line(2, 1, "tok-a", 6),
        _line(3, 2, "tok-b", 5),
        _line(4, 2, "tok-c", 7),
        _line(5, 3, "", 8),
        _line(6, 2, "unit6b-x", 9),  # excluded by the default prefix, still scanned
    ]
    # a differently-resolved token on case 1 that uses product 5 isolates it away from tok-a
    isolation = [_line(10, 1, "other", 5, customer_id=20)]
    case_pos = [(1, 101), (2, 102), (3, 103)]
    ships = _CountingList(
        [(101, 6, 30, None), (101, 5, 31, None), (102, 7, OC, None), (103, 8, 32, None)]
    )
    for i in range(extra_tokens):
        unresolved.append(_line(100 + i, 4, f"aa-{i:05d}", 50 + i))
    if extra_tokens >= 500:
        for i in range(20):  # two lines each: they sort ahead of one-line tokens on the page
            unresolved.append(_line(5000 + 2 * i, 4, f"zz-hi-{i:02d}", 700 + i))
            unresolved.append(_line(5001 + 2 * i, 4, f"zz-hi-{i:02d}", 700 + i))
    customers = [SimpleNamespace(id=c, name=f"Cust {c}", code=None) for c in (11, 12, 30, 31, 32, OC)]
    return _Db(unresolved=unresolved, isolation=isolation, case_pos=case_pos, customers=customers), ships


@pytest.fixture
def patched(monkeypatch):
    calls: dict[str, Any] = {"preview": []}

    async def oc(_db):
        return OC

    async def aliases(_db, **_kw):
        return [("tok-a", 11, None), ("tok-b", 11, None), ("tok-b", 12, None)]

    async def dist_maps(_db):
        return {}, {}

    async def preview(_db, *, norm_tokens, limit_tokens):
        calls["preview"].append((list(norm_tokens), limit_tokens))
        return {"items": [{"norm_token": t, "ship_corroboration_offer": {"for": t}} for t in norm_tokens]}

    monkeypatch.setattr(mod, "get_open_channel_customer_id", oc)
    monkeypatch.setattr(mod, "_load_approved_alias_rows", aliases)
    monkeypatch.setattr(mod, "_load_distributor_match_maps", dist_maps)
    from app.services.commercial_planner import lineup_distributor_attribution as attribution

    monkeypatch.setattr(attribution, "preview_distributor_confirmer", preview)
    return calls


def _run(db, ships, monkeypatch, **kw):
    async def ship_rows(_db, po_ids, **_kw):
        return ships

    monkeypatch.setattr(mod, "_live_ship_rows_for_pos", ship_rows)
    return asyncio.run(mod.list_customer_token_worklist(db, **kw))


def test_classification_counts_and_order_are_unchanged(patched, monkeypatch) -> None:
    db, ships = _world()
    out = _run(db, ships, monkeypatch, limit=200)
    assert [it["item_key"] for it in out["items"]] == [
        "__empty_token__:case:3",
        "tok-a",
        "tok-b",
        "tok-c",
    ]
    by = {it["item_key"]: it for it in out["items"]}
    assert by["tok-a"]["bucket"] == "genuine_conflict"
    assert by["tok-a"]["line_count"] == 2
    assert by["tok-a"]["competing_customer_ids"] == [11, 30]  # alias 11 + ship 30; ship 31 isolated away
    assert by["tok-b"]["bucket"] == "genuine_conflict"
    assert by["tok-c"]["bucket"] == "clean"
    assert by["tok-c"]["free_target_allowed"] is True
    assert by["__empty_token__:case:3"]["bucket"] == "empty_token"
    assert out["bucket_counts"] == {"genuine_conflict": 2, "clean": 1, "empty_token": 1, "all": 4}
    assert out["total"] == 4
    assert out["rows_scanned"] == 6
    assert out["open_channel_customer_id"] == OC
    assert out["exclude_prefix"] == "unit6b-"
    assert [c["meta"]["customer_id"] for c in by["tok-a"]["alias_candidates"]] == [11, 30]
    assert by["tok-a"]["alias_candidates"][0]["label"] == "Cust 11 (id 11)"
    assert by["tok-c"]["ship_corroboration_offer"] == {"for": "tok-c"}


def test_limit_cuts_the_page_but_not_the_counts(patched, monkeypatch) -> None:
    db, ships = _world()
    out = _run(db, ships, monkeypatch, limit=2)
    assert [it["item_key"] for it in out["items"]] == ["__empty_token__:case:3", "tok-a"]
    assert out["total"] == 4
    assert out["bucket_counts"] == {"genuine_conflict": 2, "clean": 1, "empty_token": 1, "all": 4}


def test_offers_are_only_computed_for_the_returned_page(patched, monkeypatch) -> None:
    db, ships = _world()
    out = _run(db, ships, monkeypatch, limit=2)  # tok-c (the only offer token) is not on the page
    assert patched["preview"] == []
    assert all(it["ship_corroboration_offer"] is None for it in out["items"])

    db, ships = _world()
    patched["preview"].clear()
    _run(db, ships, monkeypatch, limit=4)
    assert patched["preview"] == [(["tok-c"], 1)]


def test_only_the_first_500_offer_tokens_ever_get_an_offer(patched, monkeypatch) -> None:
    """The confirmer preview caps at 500 tokens in token order; the page keeps that exact rule."""
    db, ships = _world(extra_tokens=520)
    out = _run(db, ships, monkeypatch, limit=500)
    offered = {it["item_key"] for it in out["items"] if it["ship_corroboration_offer"] is not None}
    shown = {it["item_key"] for it in out["items"]}
    # 520 aa- tokens sort first, so only aa-00000..aa-00499 are among the first 500 offer tokens;
    # the two-line zz-hi- tokens are on the page (more lines sort first) but past the cap.
    assert "zz-hi-00" in shown and "zz-hi-00" not in offered
    assert "aa-00000" in offered
    assert all(f"aa-{i:05d}" in offered for i in range(0, 470) if f"aa-{i:05d}" in shown)
    assert "aa-00500" not in offered
    sent = [t for call in patched["preview"] for t in call[0]]
    assert len(sent) == len(set(sent)) and set(sent) == offered


def test_shipment_rows_are_indexed_once_not_scanned_per_token(patched, monkeypatch) -> None:
    _CountingList.iterations = 0
    db, ships = _world(extra_tokens=300)
    _run(db, ships, monkeypatch, limit=10)
    assert _CountingList.iterations == 1


def test_reads_are_bounded_columns_and_a_fixed_number_of_statements(patched, monkeypatch) -> None:
    db, ships = _world(extra_tokens=300)
    _run(db, ships, monkeypatch, limit=10)
    assert len(db.sql) <= 4  # unresolved lines, isolation lines, case POs, labels; never per token
    unresolved = next(s for s in db.sql if "commercial_lineup_line.customer_id IS NULL" in s)
    isolation = next(s for s in db.sql if "FROM commercial_lineup_line" in s and s is not unresolved)
    for sql in (unresolved, isolation):
        for wide in ("raw_row_payload", "pricing_chain_json", "month_split_json", "internal_notes"):
            assert wide not in sql  # no full ORM rows
    # isolation only ever reads lines that can isolate a product: resolved, tokened, with a product
    assert "commercial_lineup_line.customer_id IS NOT NULL" in isolation
    assert "commercial_lineup_line.customer_token IS NOT NULL" in isolation
    assert "commercial_lineup_line.product_id IS NOT NULL" in isolation
    label_sql = next(s for s in db.sql if "FROM dim_customer" in s)
    assert "dim_customer.id IN" in label_sql

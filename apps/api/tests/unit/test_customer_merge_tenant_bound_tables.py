"""B-3: a customer merge repoints rows in tenant-bound row-security tables truthfully.

``customer_calendar_event`` forces row security on ``cip.customer_calendar_tenant_id``.
Without that setting the merge's counts read 0, so the table was skipped and
``_assert_zero_loser_refs`` passed over live references. The fake session models forced
row security: a statement on the table sees rows only while the tenant setting is bound.
The merge binds the customers' tenant, restores the caller's value, and refuses when it
cannot know a single tenant. DB twin: ``tests/test_customer_merge_calendar_db.py``.
"""

from __future__ import annotations

import pytest
from app.services import customer_full_repoint as mod

GUC = "cip.customer_calendar_tenant_id"
TABLE = "customer_calendar_event"


class _Result:
    def __init__(self, value=None, rowcount: int = 0) -> None:
        self._value = value
        self.rowcount = rowcount

    def scalar(self):
        return self._value


class _Nested:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeDb:
    """Rows live on customer 1 (the loser). Visible only while the GUC equals the row tenant."""

    def __init__(self, *, tenant: str = "t1", bound: str | None = None) -> None:
        self.row_tenant = tenant
        self.gucs: dict[str, str | None] = {GUC: bound}
        self.loser_rows = 3
        self.keeper_rows = 0
        self.log: list[str] = []

    def begin_nested(self) -> _Nested:
        return _Nested()

    def flush(self) -> None:
        return None

    def _visible(self) -> bool:
        return self.gucs.get(GUC) == self.row_tenant

    def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.log.append(sql)
        if "current_setting" in sql:
            return _Result(self.gucs.get(params["g"]))
        if "set_config" in sql:
            self.gucs[params["g"]] = params["t"]
            return _Result(params["t"])
        if sql.startswith(f"SELECT count(*) FROM {TABLE}"):
            if not self._visible():
                return _Result(0)
            return _Result(
                self.loser_rows
                if params["cid" if "cid" in params else "lid"] == 1
                else self.keeper_rows
            )
        if sql.startswith(f"UPDATE {TABLE}"):
            if not self._visible():
                return _Result(rowcount=0)
            moved, self.loser_rows = self.loser_rows, 0
            self.keeper_rows += moved
            return _Result(rowcount=moved)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    monkeypatch.setattr(mod, "discover_customer_fk_columns", lambda _db: ((TABLE, "customer_id"),))
    monkeypatch.setattr(mod, "extra_customer_ref_specs", lambda: ())
    monkeypatch.setattr(
        mod,
        "_repoint_customer_aliases_with_dedup",
        lambda *_a, **_k: {"updated": 0, "deleted_dup": 0},
    )
    monkeypatch.setattr(
        mod, "_repoint_unique_per_customer_row", lambda *_a, **_k: {"updated": 0, "deleted_dup": 0}
    )
    monkeypatch.setattr(mod, "_repoint_import_mapping_candidates", lambda *_a, **_k: 0)
    tenants = {1: "t1", 2: "t1"}
    monkeypatch.setattr(mod, "_customer_tenant", lambda _db, cid: tenants.get(int(cid)))
    return tenants


def test_count_sees_tenant_bound_rows_and_restores_the_callers_setting() -> None:
    db = _FakeDb(bound="caller-tenant")
    assert mod.count_customer_fk_refs(db, 1) == {f"{TABLE}.customer_id": 3}
    assert db.gucs[GUC] == "caller-tenant"


def test_count_leaves_an_unset_setting_unset() -> None:
    db = _FakeDb(bound=None)
    mod.count_customer_fk_refs(db, 1)
    assert db.gucs[GUC] in (None, "")


def test_repoint_moves_calendar_rows_to_the_keeper_and_proves_zero_loser_refs() -> None:
    db = _FakeDb()
    stats = mod.repoint_customer_footprint_full(db, loser_id=1, keeper_id=2)
    assert stats["table_updates"] == {f"{TABLE}.customer_id": 3}
    assert db.loser_rows == 0 and db.keeper_rows == 3
    assert db.gucs[GUC] in (None, "")


def test_repoint_aborts_when_rows_cannot_be_moved(monkeypatch) -> None:
    """An UPDATE that moves fewer rows than counted must abort, not pass."""
    db = _FakeDb()
    original = db.execute

    def short_update(stmt, params=None):
        if str(stmt).strip().startswith("UPDATE"):
            return _Result(rowcount=1)
        return original(stmt, params)

    db.execute = short_update  # type: ignore[method-assign]
    with pytest.raises(mod.CustomerFullRepointAbortError):
        mod.repoint_customer_footprint_full(db, loser_id=1, keeper_id=2)


def test_repoint_refuses_when_loser_and_keeper_tenants_differ(_wire) -> None:
    _wire[2] = "t2"
    db = _FakeDb()
    with pytest.raises(mod.CustomerFullRepointAbortError) as caught:
        mod.repoint_customer_footprint_full(db, loser_id=1, keeper_id=2)
    assert "tenant" in str(caught.value)
    assert db.loser_rows == 3


def test_repoint_refuses_when_the_tenant_is_blank(_wire) -> None:
    _wire[1] = "  "
    db = _FakeDb()
    with pytest.raises(mod.CustomerFullRepointAbortError) as caught:
        mod.repoint_customer_footprint_full(db, loser_id=1, keeper_id=2)
    assert "tenant" in str(caught.value)


def test_no_tenant_bound_table_means_no_tenant_lookup(monkeypatch) -> None:
    monkeypatch.setattr(
        mod, "discover_customer_fk_columns", lambda _db: (("some_fact", "customer_id"),)
    )

    def boom(_db, _cid):
        raise AssertionError("tenant must not be read when no tenant-bound table is involved")

    monkeypatch.setattr(mod, "_customer_tenant", boom)

    class _Plain(_FakeDb):
        def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if sql.startswith("SELECT count(*) FROM some_fact"):
                return _Result(0)
            return super().execute(stmt, params)

    assert mod.count_customer_fk_refs(_Plain(), 1) == {}

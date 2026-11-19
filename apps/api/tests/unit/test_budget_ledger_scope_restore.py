"""C-1: ``_select_across_product_lines`` always puts the caller's product-line scope back.

The helper opens ``cip.product_lines`` to ``'*'`` for one read. It used to restore the
caller's scope only on success or ProgrammingError, so any other database error (a
statement timeout is OperationalError) left the scope open for the rest of the
transaction. The fake session below models Postgres: ``set_config(.., true)`` is
transaction-local, and rolling back a savepoint undoes the setting made inside it.
"""

from __future__ import annotations

import pytest
from app.models.budget_ledger import BudgetLedgerEntry
from app.services import budget_ledger
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError


class _Nested:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self._snapshot = session.scope
        self.closed = False

    def commit(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        self.closed = True
        self._session.scope = self._snapshot


class _FakeSession:
    def __init__(self, scope: str | None, fail_with: BaseException | None = None) -> None:
        self.scope = scope
        self.fail_with = fail_with
        self.nested: list[_Nested] = []

    def begin_nested(self) -> _Nested:
        nested = _Nested(self)
        self.nested.append(nested)
        return nested

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "current_setting" in sql:
            return _Result(self.scope)
        if "set_config" in sql:
            self.scope = (params or {}).get("saved", "*")
            if "'*'" in sql:
                self.scope = "*"
            return _Result(None)
        if self.fail_with is not None:
            raise self.fail_with
        return _Result([("commit", 5, None)])


class _Result:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value

    def all(self):
        return self._value


_STMT = select(BudgetLedgerEntry.entry_type)


def test_scope_restored_after_success() -> None:
    session = _FakeSession("line-a")
    assert budget_ledger._select_across_product_lines(session, _STMT) == [("commit", 5, None)]
    assert session.scope == "line-a"


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("select", {}, Exception("canceling statement due to statement timeout")),
        RuntimeError("boom"),
    ],
)
def test_scope_restored_when_a_non_programming_error_is_raised(error: BaseException) -> None:
    session = _FakeSession("line-a", fail_with=error)
    with pytest.raises(type(error)):
        budget_ledger._select_across_product_lines(session, _STMT)
    assert session.scope == "line-a"
    assert all(nested.closed for nested in session.nested)


def test_programming_error_still_means_table_missing_and_scope_restored() -> None:
    session = _FakeSession(
        "line-a", fail_with=ProgrammingError("select", {}, Exception("no table"))
    )
    assert budget_ledger._select_across_product_lines(session, _STMT) is None
    assert session.scope == "line-a"


def test_unset_scope_is_restored_as_unset() -> None:
    session = _FakeSession(None, fail_with=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        budget_ledger._select_across_product_lines(session, _STMT)
    assert session.scope is None

"""Count actual cursor executes on the async engine (one round trip per execute)."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class SqlExecuteCounter:
    """Records each SQL statement sent to the database on the instrumented engine."""

    statements: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.statements)

    def reset(self) -> None:
        self.statements.clear()

    def summary(self) -> str:
        return f"{self.count} statement(s)"


_LISTENER_BY_ENGINE_ID: dict[int, Any] = {}


def _normalize_statement(statement: str) -> str:
    return re.sub(r"\s+", " ", statement.strip())[:240]


def install_sql_counter(engine: Any) -> SqlExecuteCounter:
    """Attach a before_cursor_execute listener to the engine's sync dialect engine."""
    sync_engine: Engine = engine.sync_engine
    eid = id(sync_engine)
    counter = SqlExecuteCounter()
    if eid in _LISTENER_BY_ENGINE_ID:
        event.remove(sync_engine, "before_cursor_execute", _LISTENER_BY_ENGINE_ID[eid])

    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        counter.statements.append(_normalize_statement(statement))

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    _LISTENER_BY_ENGINE_ID[eid] = _before_cursor_execute
    return counter


def uninstall_sql_counter(engine: Any) -> None:
    sync_engine: Engine = engine.sync_engine
    eid = id(sync_engine)
    listener = _LISTENER_BY_ENGINE_ID.pop(eid, None)
    if listener is not None:
        event.remove(sync_engine, "before_cursor_execute", listener)


@contextmanager
def sql_counter_scope(engine: Any) -> Iterator[SqlExecuteCounter]:
    counter = install_sql_counter(engine)
    try:
        yield counter
    finally:
        uninstall_sql_counter(engine)

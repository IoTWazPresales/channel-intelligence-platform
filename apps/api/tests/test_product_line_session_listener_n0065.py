"""N-0065 / D-0056 round 2: every ORM transaction gets the request's product-line scope.

GOV-008 (RUN-20261007-N0065-VER) found that request handlers which open their own
``SessionLocal()`` never had ``cip.product_lines`` set, so the database gate read
them as unset (open). The fix is a Session ``after_begin`` listener. These tests
need no database: an in-memory SQLite engine with a stand-in ``set_config`` function
records the statements the listener issues.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.concurrency import run_in_threadpool

from app.core.product_line_scope import (
    _bind_scope_on_begin,
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
    request_role,
)
from app.db.session import AsyncSessionLocal
from app.db.session_sync import SessionLocal


@pytest.fixture()
def recording_engine():
    """SQLite engine with set_config(name, value, is_local) and a statement log."""
    # One shared connection so the thread hand-off tests can use it from worker threads.
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    calls: list[tuple[str, object]] = []

    @event.listens_for(eng, "connect")
    def _fn(dbapi_conn, _rec):  # type: ignore[no-untyped-def]
        dbapi_conn.create_function("set_config", 3, lambda name, value, local: value)

    @event.listens_for(eng, "before_cursor_execute")
    def _log(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if "set_config" in statement:
            calls.append((statement, parameters))

    yield eng, calls
    eng.dispose()


@contextmanager
def _scope(read: frozenset[str] | None, edit: frozenset[str] | None) -> Iterator[None]:
    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        yield
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)


def _bound_all(calls: list[tuple[str, object]]) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for _sql, params in calls:
        out.append(tuple(params) if isinstance(params, (tuple, list)) else tuple(params.values()))  # type: ignore[union-attr]
    return out


def _bound_values(calls: list[tuple[str, object]]) -> list[tuple[str, ...]]:
    """(read, edit) per bind; the role (round 4) is checked by the role tests below."""
    return [v[:2] for v in _bound_all(calls)]


def test_scoped_bind_also_writes_the_request_role(recording_engine) -> None:
    """Round 4 (0026): the same statement binds cip.request_role, transaction-local, every time."""
    eng, calls = recording_engine
    t = request_role.set("steward")
    try:
        with _scope(frozenset({"NB"}), frozenset()):
            with SessionLocal(bind=eng) as s:
                s.execute(text("select 1"))
                s.commit()
                s.execute(text("select 2"))
    finally:
        request_role.reset(t)
    assert "cip.request_role" in calls[0][0]
    assert _bound_all(calls) == [("NB", "!", "steward")] * 2


def test_scoped_bind_without_a_role_writes_empty_role(recording_engine) -> None:
    """A scoped transaction never keeps another request's role from a pooled backend."""
    eng, calls = recording_engine
    assert request_role.get() is None
    with _scope(frozenset(), frozenset()):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
    assert _bound_all(calls) == [("!", "!", "")]


def test_listener_is_registered_for_sync_and_async_sessions() -> None:
    assert event.contains(Session, "after_begin", _bind_scope_on_begin)
    # SessionLocal() builds plain Session objects; AsyncSession wraps a Session subclass.
    assert issubclass(SessionLocal.class_, Session)
    sync_cls = AsyncSessionLocal.kw.get("sync_session_class", Session)
    assert issubclass(sync_cls, Session)


def test_sessionlocal_under_empty_scope_issues_set_config(recording_engine) -> None:
    eng, calls = recording_engine
    with _scope(*product_line_scope_for(is_admin=False, assignments=[])):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
    assert len(calls) == 1
    assert "cip.product_lines" in calls[0][0] and "cip.editable_product_lines" in calls[0][0]
    assert "true" in calls[0][0].lower()  # transaction-local, never session-wide
    assert _bound_values(calls) == [("!", "!")]


def test_half_set_scope_binds_the_missing_side_as_no_lines(recording_engine) -> None:
    """Round 3: a scoped transaction writes both settings, never leaving one at a leftover ''
    (open from 0025). A missing side is the '!' sentinel (no lines)."""
    eng, calls = recording_engine
    for read, edit in ((frozenset({"NB"}), None), (None, frozenset({"NB"}))):
        with _scope(read, edit):
            with SessionLocal(bind=eng) as s:
                s.execute(text("select 1"))
    assert _bound_values(calls) == [("NB", "!"), ("!", "NB")]


def test_sessionlocal_read_only_line_binds_read_and_edit_separately(recording_engine) -> None:
    eng, calls = recording_engine
    read, edit = product_line_scope_for(is_admin=False, assignments=[("NB", False), ("Monitor", True)])
    with _scope(read, edit):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
    assert _bound_values(calls) == [("Monitor,NB", "Monitor")]


def test_scope_is_rebound_after_commit(recording_engine) -> None:
    eng, calls = recording_engine
    with _scope(*product_line_scope_for(is_admin=True, assignments=[])):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
            s.commit()
            s.execute(text("select 2"))
            s.rollback()
            s.execute(text("select 3"))
    # One bind per transaction: before the commit, after it, and after the rollback.
    assert _bound_values(calls) == [("*", "*")] * 3


def test_savepoint_is_not_rebound(recording_engine) -> None:
    eng, calls = recording_engine
    with _scope(frozenset({"NB"}), frozenset()):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
            with s.begin_nested():
                s.execute(text("select 2"))
    assert _bound_values(calls) == [("NB", "!")]


def test_worker_with_unset_scope_issues_nothing(recording_engine) -> None:
    eng, calls = recording_engine
    assert request_product_lines.get() is None and request_editable_product_lines.get() is None
    with SessionLocal(bind=eng) as s:
        s.execute(text("select 1"))
        s.commit()
        s.execute(text("select 2"))
    assert calls == []


def test_worker_on_a_previously_scoped_pooled_connection_is_bound_open(recording_engine) -> None:
    """After a scoped transaction Postgres leaves the setting at '', not NULL.

    Under 0024 '' meant "no lines"; from 0025 it is open. A later unscoped user of the same
    pooled connection (an in-process background thread) must stay open under both, so the
    listener binds '*' there; on a fresh connection it binds nothing.
    """
    eng, calls = recording_engine
    with _scope(frozenset(), frozenset()):
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
    with SessionLocal(bind=eng) as s:  # same StaticPool connection, worker context
        s.execute(text("select 1"))
    assert len(calls) == 2
    assert _bound_values(calls)[0] == ("!", "!")
    assert "'*'" in calls[1][0] and "cip.editable_product_lines" in calls[1][0]


def test_threadpool_handoffs_carry_the_scope(recording_engine) -> None:
    """Starlette's run_in_threadpool (sync endpoints) and asyncio.to_thread copy the context."""
    eng, calls = recording_engine

    def work() -> None:
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))

    async def go() -> None:
        with _scope(frozenset(), frozenset()):
            await run_in_threadpool(work)
            await asyncio.to_thread(work)

    asyncio.run(go())
    assert _bound_values(calls) == [("!", "!")] * 2


def test_plain_thread_starts_unscoped_like_a_worker(recording_engine) -> None:
    """A bare threading.Thread starts with an empty context (Python 3.12), i.e. worker scope.

    The in-process background fallback (task_run_ledger.spawn_in_process_thread_with_ledger)
    therefore runs exactly like its Celery counterpart: unset, gate open.
    """
    eng, calls = recording_engine

    def work() -> None:
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))

    with _scope(frozenset(), frozenset()):
        t = threading.Thread(target=work)
        t.start()
        t.join()
    assert calls == []


def test_sync_fastapi_endpoint_sees_scope_bound_by_async_dependency(recording_engine) -> None:
    """End to end through FastAPI: an async yield dependency (like _bind_request_tenant) binds
    the scope, then a plain ``def`` endpoint opens SessionLocal() in the threadpool."""
    eng, calls = recording_engine
    app = FastAPI()

    async def bind_scope():
        with _scope(frozenset({"NB"}), frozenset()):
            yield

    @app.get("/probe", dependencies=[Depends(bind_scope)])
    def probe() -> dict:
        with SessionLocal(bind=eng) as s:
            s.execute(text("select 1"))
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/probe").status_code == 200
    assert _bound_values(calls) == [("NB", "!")]
    # The request's scope did not leak into this (test) context.
    assert request_product_lines.get() is None

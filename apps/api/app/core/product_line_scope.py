"""Product-line read and edit scope for a signed-in user (D-0056).

An admin sees and edits every product line; no assignment is needed. Anyone
else sees only the lines assigned to them, and no assignment means no product
data. Each assigned line is either read-only or read and edit. Workers and
forged test identities leave the scope unset, so their existing reads stay
unchanged.

Database setting values (migration 20261007_0025): NULL or '' = open (workers;
'' is what a pooled backend keeps after a scoped transaction), '*' = every line,
NO_PRODUCT_LINES ('!') = no lines, 'A,B' = only those lines. The app never writes
'' for a signed-in user: "no lines" is always the sentinel. Under 0024 the
sentinel is a line nobody has, so it also means "no lines" there.

A scoped transaction also binds ``cip.request_role`` to the signed-in user's
server-side role (migration 20261009_0026). Shipment evidence rows with no
product that cannot inherit a line from their identity are visible only under
an open scope or to the 'steward' role. Workers leave it unset; they are open.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextvars import ContextVar
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# None: do not set the database gate. Empty: the user may see no product lines.
# ALL_PRODUCT_LINES ('*'): every line; the database functions read '*' as all.
ALL_PRODUCT_LINES: frozenset[str] = frozenset({"*"})
# What an empty scope is written as. Never '' (from 0025 the database reads '' as unset).
NO_PRODUCT_LINES = "!"

request_product_lines: ContextVar[frozenset[str] | None] = ContextVar(
    "cip_request_product_lines", default=None
)
request_editable_product_lines: ContextVar[frozenset[str] | None] = ContextVar(
    "cip_request_editable_product_lines", default=None
)
# Server-side role of the signed-in user ('admin', 'steward', 'planner', 'viewer'),
# set by the router next to the product lines. None for workers.
request_role: ContextVar[str | None] = ContextVar("cip_request_role", default=None)


def product_line_scope_for(
    *, is_admin: bool, assignments: Iterable[tuple[object, bool]]
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the (read, edit) product lines for a signed-in user.

    ``assignments`` holds (product_line, can_edit) pairs. An admin gets every
    line for read and edit whatever the assignments say. For anyone else a
    stored '*', the sentinel '!' or a line holding a comma is ignored, so one
    grant row can never widen to all lines, split into several lines in the
    database setting, or be read as the "no lines" sentinel.
    """
    if is_admin:
        return ALL_PRODUCT_LINES, ALL_PRODUCT_LINES
    read: set[str] = set()
    edit: set[str] = set()
    for raw_line, can_edit in assignments:
        line = str(raw_line or "").strip()
        if not line or line in ("*", NO_PRODUCT_LINES) or "," in line:
            continue
        read.add(line)
        if can_edit:
            edit.add(line)
    return frozenset(read), frozenset(edit)


def scope_csv(lines: frozenset[str] | None) -> str | None:
    """Setting value for a scope: None stays unset; empty becomes the '!' sentinel."""
    if lines is None:
        return None
    return ",".join(sorted(lines)) or NO_PRODUCT_LINES


_SCOPE_SQL = (
    "SELECT set_config('cip.product_lines', :cip_pl_read, true), "
    "set_config('cip.editable_product_lines', :cip_pl_edit, true), "
    "set_config('cip.request_role', :cip_pl_role, true)"
)


def _scope_params() -> dict[str, str] | None:
    """The setting values for the current request, or None when the scope is unset.

    When either side is set, both are written, and a missing side is "no lines".
    A scoped transaction therefore never runs on a leftover '' (open from 0025).
    The role is always written too ('' when unknown), so a scoped transaction never
    inherits another request's role from a pooled backend.
    """
    read = request_product_lines.get()
    edit = request_editable_product_lines.get()
    if read is None and edit is None:
        return None
    return {
        "cip_pl_read": scope_csv(read) or NO_PRODUCT_LINES,
        "cip_pl_edit": scope_csv(edit) or NO_PRODUCT_LINES,
        "cip_pl_role": (request_role.get() or "").strip().lower(),
    }


def product_line_scope_statement() -> tuple[str, dict[str, str]] | None:
    """One SELECT that binds the current request scope to the open transaction.

    None when the scope is unset (workers, scripts, login before the user is
    known): the database gate then stays open, as before.
    """
    params = _scope_params()
    if params is None:
        return None
    return _SCOPE_SQL, params


# Marks a pooled DBAPI connection (Connection.info lives as long as it does) that has
# carried a request scope. After that transaction ends, Postgres keeps the custom
# setting defined with the value '', not NULL. From 0025 the gate reads '' as open;
# under 0024 it read '' as "no lines". Binding '*' explicitly is right under both.
_SCOPED_BEFORE = "cip_product_line_scoped_before"
_OPEN_SQL = (
    "SELECT set_config('cip.product_lines', '*', true), "
    "set_config('cip.editable_product_lines', '*', true)"
)


def _bind_scope_on_begin(session: Any, transaction: Any, connection: Any) -> None:
    """Session ``after_begin``: every ORM transaction, sync or async, gets the scope.

    ``set_config(..., true)`` is transaction-local, so the scope ends at commit
    or rollback and can never reach another request through the pool. Because
    this runs again at the start of the next transaction, the scope also
    survives a commit followed by more reads in the same request. A savepoint
    inherits the outer transaction's setting, so it is not re-bound.

    A scoped transaction always writes both settings, with the '!' sentinel for
    "no lines", so it never runs on a leftover '' (which is open from 0025).

    Unset scope (workers, scripts, the in-process background threads) stays
    open. On a fresh connection that needs no statement. On a pooled connection
    that served a request before, the open scope is bound explicitly as '*'.
    From 0025 the gate treats '*', '' and unset the same; under 0024 the
    leftover '' would have hidden every product.
    """
    if getattr(transaction, "nested", False):
        return
    stmt = product_line_scope_statement()
    if stmt is None:
        if connection.info.get(_SCOPED_BEFORE):
            connection.execute(text(_OPEN_SQL))
        return
    sql, params = stmt
    connection.info[_SCOPED_BEFORE] = True
    connection.execute(text(sql), params)


def install_product_line_transaction_scope() -> None:
    """Register the ``after_begin`` listener once, on the base ORM ``Session`` class.

    The base class covers ``SessionLocal()`` (sync) and ``AsyncSession`` (its
    ``sync_session_class`` is ``Session``), so every session factory in the app
    is scoped. Called from both session modules; idempotent.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    if not event.contains(Session, "after_begin", _bind_scope_on_begin):
        event.listen(Session, "after_begin", _bind_scope_on_begin)


async def apply_product_line_guc(session: AsyncSession) -> None:
    """Bind the request scope to the transaction that is already open.

    New transactions are bound by the ``after_begin`` listener. This is only
    needed when a transaction began before the scope was known (the router's
    own access-row lookup). Unset scope leaves the gate open. Both settings are
    written, as in the listener.
    """
    params = _scope_params()
    if params is None:
        return
    await session.execute(text(_SCOPE_SQL), params)


async def widen_product_line_catalog(session: AsyncSession) -> None:
    """Let an admin list every product line so they can assign one."""
    await session.execute(text("SELECT set_config('cip.product_lines', '*', true)"))
    await session.execute(text("SELECT set_config('cip.editable_product_lines', '*', true)"))

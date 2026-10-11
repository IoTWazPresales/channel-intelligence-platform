"""N-0065 / D-0056: product-line scope for a signed-in user.

An admin sees and edits every product line without an assignment. Anyone else
sees only assigned lines (none when there is no assignment), and a read-only
line is not editable. Workers and forged identities leave the scope unset.

No database: the router dependency runs against a recording fake session.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.router import _bind_request_tenant
from app.core.product_line_scope import (
    ALL_PRODUCT_LINES,
    NO_PRODUCT_LINES,
    apply_product_line_guc,
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
    request_role,
    scope_csv,
)
from app.core.security import Role


# --- pure helper -------------------------------------------------------------------------


def test_admin_with_no_rows_gets_every_line_for_read_and_edit() -> None:
    read, edit = product_line_scope_for(is_admin=True, assignments=[])
    assert read == ALL_PRODUCT_LINES == frozenset({"*"})
    assert edit == ALL_PRODUCT_LINES
    assert scope_csv(read) == "*"


def test_admin_ignores_assignment_rows() -> None:
    read, edit = product_line_scope_for(is_admin=True, assignments=[("NB", False)])
    assert read == edit == frozenset({"*"})


def test_non_admin_with_no_rows_sees_nothing() -> None:
    read, edit = product_line_scope_for(is_admin=False, assignments=[])
    assert read == frozenset() and edit == frozenset()
    # Empty, not None: the database gate gets the '!' sentinel and shows no product rows.
    # Never '': from migration 0025 the database reads '' as unset (open).
    assert scope_csv(read) == "!" == NO_PRODUCT_LINES
    assert scope_csv(None) is None


def test_non_admin_sentinel_row_is_ignored() -> None:
    read, edit = product_line_scope_for(is_admin=False, assignments=[("!", True), ("NB", True)])
    assert read == edit == frozenset({"NB"})


def test_non_admin_read_only_line_is_not_editable() -> None:
    read, edit = product_line_scope_for(
        is_admin=False, assignments=[("NB", False), (" Monitor ", True), ("", True), (None, True)]
    )
    assert read == frozenset({"NB", "Monitor"})
    assert edit == frozenset({"Monitor"})
    assert "NB" not in edit


def test_non_admin_star_or_comma_row_never_widens_scope() -> None:
    read, edit = product_line_scope_for(
        is_admin=False, assignments=[("*", True), ("NB,Monitor", True), ("Phone", False)]
    )
    assert read == frozenset({"Phone"})
    assert edit == frozenset()


# --- router dependency -------------------------------------------------------------------


class _FakeSession:
    """Records statements; answers the access-row select with the given rows."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.selects = 0
        self.set_config: list[tuple[str, str]] = []
        self.roles: list[str | None] = []

    async def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
        sql = str(stmt)
        if "set_config" in sql:
            # One statement binds both settings (read first, then edit) and, from round 4,
            # the request role.
            assert "cip.product_lines" in sql and "cip.editable_product_lines" in sql, sql
            assert "cip.request_role" in sql, sql
            self.set_config.append(("cip.product_lines", (params or {}).get("cip_pl_read")))
            self.set_config.append(("cip.editable_product_lines", (params or {}).get("cip_pl_edit")))
            self.roles.append((params or {}).get("cip_pl_role"))
            return MagicMock()
        if "user_product_line_access" in sql:
            self.selects += 1
            result = MagicMock()
            result.scalars.return_value.all.return_value = self.rows
            return result
        raise AssertionError(f"unexpected statement: {sql}")


def _run_dependency(user: dict, db: _FakeSession):
    """Enter the dependency, capture the bound scope, then exit it."""

    async def go():
        gen = _bind_request_tenant(user=user, db=db)
        await gen.__anext__()
        seen = (request_product_lines.get(), request_editable_product_lines.get())
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        after = (request_product_lines.get(), request_editable_product_lines.get())
        return seen, after

    return asyncio.run(go())


def _row(line: str, can_edit: bool) -> SimpleNamespace:
    return SimpleNamespace(product_line=line, can_edit=can_edit)


def test_dependency_admin_without_rows_binds_star_and_skips_lookup() -> None:
    db = _FakeSession(rows=[])
    seen, after = _run_dependency({"id": "7", "role": Role.ADMIN, "tenant_id": "default"}, db)
    assert seen == (frozenset({"*"}), frozenset({"*"}))
    assert db.selects == 0
    assert db.set_config == [("cip.product_lines", "*"), ("cip.editable_product_lines", "*")]
    assert after == (None, None)


def test_dependency_admin_role_as_plain_string_is_admin() -> None:
    db = _FakeSession(rows=[])
    seen, _ = _run_dependency({"id": "7", "role": "admin", "tenant_id": "default"}, db)
    assert seen == (frozenset({"*"}), frozenset({"*"}))


def test_dependency_non_admin_without_rows_binds_empty() -> None:
    for role in (Role.STEWARD, Role.PLANNER, Role.VIEWER):
        db = _FakeSession(rows=[])
        seen, after = _run_dependency({"id": "8", "role": role, "tenant_id": "default"}, db)
        assert seen == (frozenset(), frozenset()), role
        assert db.selects == 1
        assert db.set_config == [("cip.product_lines", "!"), ("cip.editable_product_lines", "!")]
        assert after == (None, None)


def test_dependency_non_admin_read_only_line_is_not_editable() -> None:
    db = _FakeSession(rows=[_row("NB", False), _row("Monitor", True)])
    seen, _ = _run_dependency({"id": "9", "role": Role.PLANNER, "tenant_id": "default"}, db)
    assert seen == (frozenset({"NB", "Monitor"}), frozenset({"Monitor"}))
    assert db.set_config == [
        ("cip.product_lines", "Monitor,NB"),
        ("cip.editable_product_lines", "Monitor"),
    ]


def test_dependency_forged_or_worker_identity_leaves_scope_unset() -> None:
    # Non-numeric ids (stub forge "demo-user", test identities) never bind a scope, admin or not.
    for user in (
        {"id": "demo-user", "role": Role.ADMIN, "tenant_id": "default"},
        {"id": "demo-user", "role": Role.VIEWER, "tenant_id": "default"},
        {"id": None, "role": Role.VIEWER, "tenant_id": "default"},
    ):
        db = _FakeSession(rows=[_row("NB", True)])
        seen, after = _run_dependency(user, db)
        assert seen == (None, None), user
        assert db.selects == 0 and db.set_config == []
        assert after == (None, None)


def test_dependency_binds_the_server_side_role() -> None:
    """Round 4 (0026): cip.request_role comes from the same role require_roles trusts."""
    cases = [(Role.STEWARD, "steward"), ("data_steward", "steward"), (Role.PLANNER, "planner"),
             (Role.VIEWER, "viewer"), (Role.ADMIN, "admin"), ("unknown-role", "viewer")]
    for raw, expected in cases:
        db = _FakeSession(rows=[])
        _run_dependency({"id": "8", "role": raw, "tenant_id": "default"}, db)
        assert db.roles == [expected], raw
    assert request_role.get() is None  # reset after the request


def test_dependency_forged_identity_binds_no_role() -> None:
    db = _FakeSession(rows=[])
    _run_dependency({"id": "demo-user", "role": Role.STEWARD, "tenant_id": "default"}, db)
    assert db.roles == [] and request_role.get() is None


def test_apply_guc_with_unset_scope_issues_nothing() -> None:
    db = _FakeSession(rows=[])
    asyncio.run(apply_product_line_guc(db))  # type: ignore[arg-type]
    assert db.set_config == []

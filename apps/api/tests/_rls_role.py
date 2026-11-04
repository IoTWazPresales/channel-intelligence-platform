"""Make row-security tests subject to row security.

FORCE ROW LEVEL SECURITY does not apply to a superuser or a role with
BYPASSRLS. When the session user is one of those, SET LOCAL ROLE inside the
open test transaction to a LOGIN role that is neither, then RESET ROLE before
the connection returns to the pool. If no such role exists, fail. Never skip.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

_SESSION_FLAGS = text(
    """
    SELECT r.rolname AS role, r.rolsuper AS rolsuper, r.rolbypassrls AS rolbypassrls
    FROM pg_roles r
    WHERE r.rolname = session_user
    """
)

# Prefer the app role. A superuser may assume any LOGIN role. A BYPASSRLS
# non-superuser may assume only a role it has the SET privilege on.
_LOGIN_TARGET = text(
    """
    SELECT candidate.rolname
    FROM pg_roles AS session_role
    JOIN pg_roles AS candidate ON candidate.rolcanlogin
      AND NOT candidate.rolsuper
      AND NOT candidate.rolbypassrls
      AND (
        session_role.rolsuper
        OR pg_has_role(session_role.rolname, candidate.rolname, 'SET')
      )
    WHERE session_role.rolname = session_user
    ORDER BY CASE WHEN candidate.rolname = 'cip' THEN 0 ELSE 1 END, candidate.rolname
    LIMIT 1
    """
)


def engage_nonsuperuser_role(conn) -> bool:
    """SET LOCAL ROLE when the session user bypasses row security.

    Call inside the test transaction. Returns True when the role was changed.
    """
    row = conn.execute(_SESSION_FLAGS).one()
    if not row.rolsuper and not row.rolbypassrls:
        return False
    target = conn.execute(_LOGIN_TARGET).scalar()
    if not target:
        pytest.fail(
            f"session role {row.role} rolsuper={bool(row.rolsuper)} "
            f"rolbypassrls={bool(row.rolbypassrls)} bypasses row security and no LOGIN "
            "role with rolsuper false and rolbypassrls false exists",
            pytrace=False,
        )
    conn.execute(text("SELECT set_config('role', :role, true)"), {"role": target})
    still_bypasses = conn.execute(
        text(
            """
            SELECT r.rolsuper OR r.rolbypassrls
            FROM pg_roles r
            WHERE r.rolname = current_user
            """
        )
    ).scalar_one()
    if still_bypasses:
        pytest.fail(
            f"session role {row.role} rolsuper={bool(row.rolsuper)} "
            f"rolbypassrls={bool(row.rolbypassrls)} still bypasses row security "
            f"after SET LOCAL ROLE {target}",
            pytrace=False,
        )
    return True


def release_nonsuperuser_role(conn, engaged: bool) -> None:
    """RESET ROLE before the connection returns to the pool."""
    if not engaged:
        return
    try:
        conn.execute(text("RESET ROLE"))
    except Exception:
        # An aborted transaction cannot RESET ROLE. The caller's rollback ends
        # the transaction and clears SET LOCAL before the connection is reused.
        return

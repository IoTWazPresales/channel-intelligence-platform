"""Approved source-token alias uniqueness (INT-03).

Run a conflict pre-check before upgrade — migration aborts if duplicate approved
aliases map one normalized_token scope to multiple entity ids.

Revision ID: 20260608_0048
Revises: 20260607_0047
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260608_0048"
down_revision: Union[str, Sequence[str], None] = "20260607_0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_alias_conflicts(conn) -> None:
    dist_rows = conn.execute(
        text(
            """
            SELECT normalized_token,
                   COALESCE(source_definition_id, -1) AS scope_src,
                   COUNT(DISTINCT distributor_id) AS entity_cnt
            FROM distributor_source_token_alias
            WHERE status = 'approved'
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT distributor_id) > 1
            LIMIT 5
            """
        )
    ).fetchall()
    if dist_rows:
        sample = ", ".join(f"{r[0]!r} (scope={r[1]}, entities={r[2]})" for r in dist_rows)
        raise RuntimeError(
            "Cannot add distributor alias uniqueness: conflicting approved aliases exist. "
            f"Resolve steward duplicates first. Sample: {sample}"
        )

    cust_rows = conn.execute(
        text(
            """
            SELECT normalized_token,
                   COALESCE(source_definition_id, -1) AS scope_src,
                   COALESCE(distributor_id, -1) AS scope_dist,
                   COUNT(DISTINCT customer_id) AS entity_cnt
            FROM customer_source_token_alias
            WHERE status = 'approved'
            GROUP BY 1, 2, 3
            HAVING COUNT(DISTINCT customer_id) > 1
            LIMIT 5
            """
        )
    ).fetchall()
    if cust_rows:
        sample = ", ".join(
            f"{r[0]!r} (src={r[1]}, dist={r[2]}, entities={r[3]})" for r in cust_rows
        )
        raise RuntimeError(
            "Cannot add customer alias uniqueness: conflicting approved aliases exist. "
            f"Resolve steward duplicates first. Sample: {sample}"
        )


def upgrade() -> None:
    conn = op.get_bind()
    _assert_no_alias_conflicts(conn)
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_dist_src_token_alias_approved_scope
            ON distributor_source_token_alias (
                normalized_token,
                COALESCE(source_definition_id, -1)
            )
            WHERE status = 'approved'
            """
        )
    )
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_cust_src_token_alias_approved_scope
            ON customer_source_token_alias (
                normalized_token,
                COALESCE(source_definition_id, -1),
                COALESCE(distributor_id, -1)
            )
            WHERE status = 'approved'
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS uq_cust_src_token_alias_approved_scope"))
    op.execute(text("DROP INDEX IF EXISTS uq_dist_src_token_alias_approved_scope"))

"""cpor_case_line effective window + window-aware unique grain (BACKLOG-137 / D-058).

Revision ID: 20260924_0023
Revises: 20260906_0022
Create Date: 2026-09-24

Adds ``window_start`` / ``window_end`` (DATE, NOT NULL) to ``cpor_case_line``.
Backfill copies the parent ``cpor_case`` window verbatim. Week convention is
Monday–Sunday; a case window that is not week-aligned is copied as-is (not
snapped, not pro-rated) and the settlement service flags it
(``window_week_straddle``). Settlement numbers are unchanged by the backfill.

Unique grain ``uq_cpor_case_line_grain`` gains ``window_start`` so a superseded
line and its successor for the same (case, product, distributor, pod_quarter)
can coexist. The constraint keeps its name so the historical-import upsert
(``ON CONFLICT ON CONSTRAINT uq_cpor_case_line_grain``) keeps working.

Downgrade refuses (no data loss) if any (case, product, distributor,
pod_quarter) now holds more than one window.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0023"
down_revision: Union[str, Sequence[str], None] = "20260906_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GRAIN_OLD = ["case_id", "product_id", "distributor_id", "pod_quarter"]
_GRAIN_NEW = [*_GRAIN_OLD, "window_start"]


def upgrade() -> None:
    op.add_column("cpor_case_line", sa.Column("window_start", sa.Date(), nullable=True))
    op.add_column("cpor_case_line", sa.Column("window_end", sa.Date(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE cpor_case_line AS l "
            "SET window_start = c.window_start, window_end = c.window_end "
            "FROM cpor_case AS c WHERE c.id = l.case_id"
        )
    )
    op.alter_column("cpor_case_line", "window_start", nullable=False)
    op.alter_column("cpor_case_line", "window_end", nullable=False)
    op.create_check_constraint(
        op.f("ck_cpor_case_line_window_order"),
        "cpor_case_line",
        "window_end >= window_start",
    )
    op.drop_constraint("uq_cpor_case_line_grain", "cpor_case_line", type_="unique")
    op.create_unique_constraint("uq_cpor_case_line_grain", "cpor_case_line", _GRAIN_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    collisions = bind.execute(
        sa.text(
            "SELECT count(*) FROM ("
            " SELECT case_id, product_id, distributor_id, pod_quarter"
            " FROM cpor_case_line GROUP BY 1, 2, 3, 4"
            " HAVING count(DISTINCT window_start) > 1) AS d"
        )
    ).scalar_one()
    if collisions:
        raise RuntimeError(
            f"downgrade refused: {collisions} (case, product, distributor, pod_quarter) groups "
            "hold more than one line window; the pre-0023 grain cannot store them"
        )
    op.drop_constraint("uq_cpor_case_line_grain", "cpor_case_line", type_="unique")
    op.create_unique_constraint("uq_cpor_case_line_grain", "cpor_case_line", _GRAIN_OLD)
    op.drop_constraint(op.f("ck_cpor_case_line_window_order"), "cpor_case_line", type_="check")
    op.drop_column("cpor_case_line", "window_end")
    op.drop_column("cpor_case_line", "window_start")

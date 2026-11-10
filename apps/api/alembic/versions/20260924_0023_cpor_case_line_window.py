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

Idempotent: ``20260801_0001`` create_all already has the columns, the
``window_order`` check, and ``uq_cpor_case_line_grain`` including ``window_start``.
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


def upgrade() -> None:
    op.execute("ALTER TABLE cpor_case_line ADD COLUMN IF NOT EXISTS window_start DATE")
    op.execute("ALTER TABLE cpor_case_line ADD COLUMN IF NOT EXISTS window_end DATE")
    # Only fill rows this revision just added. create_all rows already have their own window.
    op.execute(
        sa.text(
            "UPDATE cpor_case_line AS l "
            "SET window_start = c.window_start, window_end = c.window_end "
            "FROM cpor_case AS c "
            "WHERE c.id = l.case_id AND l.window_start IS NULL"
        )
    )
    op.execute("ALTER TABLE cpor_case_line ALTER COLUMN window_start SET NOT NULL")
    op.execute("ALTER TABLE cpor_case_line ALTER COLUMN window_end SET NOT NULL")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_cpor_case_line_window_order'
              AND conrelid = 'public.cpor_case_line'::regclass
          ) THEN
            ALTER TABLE cpor_case_line
              ADD CONSTRAINT ck_cpor_case_line_window_order
              CHECK (window_end >= window_start);
          END IF;
        END $$;
        """
    )
    # Rebuild the grain only when it does not already include window_start.
    # create_all's UniqueConstraint is already the new grain; dropping it would
    # only recreate the same constraint.
    op.execute(
        """
        DO $$
        DECLARE
          grain text[];
        BEGIN
          SELECT array_agg(a.attname::text ORDER BY k.ord)
            INTO grain
          FROM pg_constraint c
          JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = k.attnum
          WHERE c.conname = 'uq_cpor_case_line_grain'
            AND c.conrelid = 'public.cpor_case_line'::regclass
            AND c.contype = 'u';
          IF grain IS DISTINCT FROM ARRAY['case_id', 'product_id', 'distributor_id', 'pod_quarter', 'window_start']::text[] THEN
            ALTER TABLE cpor_case_line DROP CONSTRAINT IF EXISTS uq_cpor_case_line_grain;
            ALTER TABLE cpor_case_line
              ADD CONSTRAINT uq_cpor_case_line_grain
              UNIQUE (case_id, product_id, distributor_id, pod_quarter, window_start);
          END IF;
        END $$;
        """
    )


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
    op.execute("ALTER TABLE cpor_case_line DROP CONSTRAINT IF EXISTS uq_cpor_case_line_grain")
    op.create_unique_constraint("uq_cpor_case_line_grain", "cpor_case_line", _GRAIN_OLD)
    op.execute("ALTER TABLE cpor_case_line DROP CONSTRAINT IF EXISTS ck_cpor_case_line_window_order")
    # create_all names the same check window_order. Drop it or DROP COLUMN fails.
    op.execute("ALTER TABLE cpor_case_line DROP CONSTRAINT IF EXISTS window_order")
    op.execute("ALTER TABLE cpor_case_line DROP COLUMN IF EXISTS window_end")
    op.execute("ALTER TABLE cpor_case_line DROP COLUMN IF EXISTS window_start")

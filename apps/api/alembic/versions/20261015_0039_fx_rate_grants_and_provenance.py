"""FX: let the app role write fx_daily_rate; record how a case's booked rate was chosen.

Revision ID: 20261015_0039
Revises: 20261015_0038
Create Date: 2026-10-15

N-0083. ``20260905_0021`` created ``fx_daily_rate`` and its id sequence under the
migration role without granting them to the app role ``cip``, so the FX poller could
not read or write the table. This grants SELECT, INSERT, UPDATE on the table and
USAGE, SELECT on the sequence to ``cip`` (nothing is deleted by the app).

Adds three nullable provenance columns on ``cpor_case``. They sit beside
``roe_snapshot`` (the booked rate) and do not touch the ``fx_proposed_*`` columns:
  fx_booked_source     stored | manual_override | existing
  fx_booked_rate_date  the ECB date of the stored rate the case was booked from
  fx_override_reason   why an operator replaced the stored rate

Additive; no row is rewritten. Downgrade drops the columns and revokes the grants.

Idempotent: ``20260801_0001`` create_all already has the provenance columns.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261015_0039"
down_revision: Union[str, Sequence[str], None] = "20261015_0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON fx_daily_rate TO cip';
            EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE fx_daily_rate_id_seq TO cip';
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_booked_source VARCHAR(32)")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_booked_rate_date DATE")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_override_reason TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_override_reason")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_booked_rate_date")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_booked_source")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            EXECUTE 'REVOKE ALL ON SEQUENCE fx_daily_rate_id_seq FROM cip';
            EXECUTE 'REVOKE ALL ON fx_daily_rate FROM cip';
          END IF;
        END $$;
        """
    )

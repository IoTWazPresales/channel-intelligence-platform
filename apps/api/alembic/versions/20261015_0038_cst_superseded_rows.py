"""Customer sell-through: keep rows a re-upload of the same file supersedes.

Revision ID: 20261015_0038
Revises: 20261014_0037
Create Date: 2026-10-15

N-0110 repair. Re-loading a file loaded under older keys (sites stored as one row,
a week stored under the wrong year) wrote new rows beside the old ones and counted
units twice. The apply now moves those old rows here, verbatim (``row_json`` is the
whole fact row), with the load that superseded them. Nothing is hard-deleted:
the raw staging rows stay, and this table is the audit trail.

Additive; existing rows unchanged.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261015_0038"
down_revision: Union[str, Sequence[str], None] = "20261014_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_customer_sellthrough_superseded (
            id bigserial PRIMARY KEY,
            fact_id integer NOT NULL,
            source_key varchar(256) NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            customer_id integer NOT NULL,
            product_id integer NOT NULL,
            period_start_date date NOT NULL,
            units_sold numeric(18, 4) NOT NULL,
            reported_soh numeric(18, 4),
            import_job_id integer,
            superseded_by_import_job_id integer NOT NULL,
            reason varchar(64) NOT NULL,
            row_json jsonb NOT NULL,
            superseded_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fact_cst_superseded_by_job
            ON fact_customer_sellthrough_superseded (superseded_by_import_job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fact_cst_superseded_customer
            ON fact_customer_sellthrough_superseded (tenant_id, customer_id)
        """
    )
    # Same product-line row security as fact_customer_sellthrough (20261006_0024, D-0056).
    op.execute("ALTER TABLE fact_customer_sellthrough_superseded ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fact_customer_sellthrough_superseded FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY cip_pl_select ON fact_customer_sellthrough_superseded FOR SELECT "
        "USING (cip_product_id_visible((product_id)::bigint))"
    )
    op.execute(
        "CREATE POLICY cip_pl_insert ON fact_customer_sellthrough_superseded FOR INSERT "
        "WITH CHECK (cip_product_id_editable((product_id)::bigint))"
    )
    # Audit trail: no UPDATE or DELETE policy, so under FORCE row security an update or
    # delete matches no rows, for the owner too. Dropping the table (downgrade) still works.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT ON fact_customer_sellthrough_superseded TO cip;
            GRANT USAGE, SELECT ON SEQUENCE fact_customer_sellthrough_superseded_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fact_customer_sellthrough_superseded")

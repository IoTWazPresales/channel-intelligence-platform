"""Distributor sell-out and returns: keep the figures a reload of the same invoice line replaces.

Revision ID: 20261016_0042
Revises: 20261016_0041
Create Date: 2026-10-16

N-0111 repair (D-0110, Warren 2026-10-16). A distributor line is keyed by distributor, customer,
product, transaction date and invoice number. Reloading the same invoice line used to overwrite
units and revenue in place; the earlier figure survived only on the earlier load's staging line.
The apply now writes the replaced figures here first, with the line and load that replaced them.
A line with a new invoice number is a new transaction and is added as before (unchanged).

Append-only like ``fact_customer_sellthrough_superseded``: SELECT and INSERT policies only, in the
inline product-line form of 20261007_0025 / 20261015_0040. Additive; existing rows unchanged. Needs
the table owner (on cip: ``postgres``), so run it with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0042"
down_revision: Union[str, Sequence[str], None] = "20261016_0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "fact_distributor_line_superseded"
COLUMN = '"product_id"'


def _inline(setting: str, line_function: str) -> str:
    return (
        f"(({COLUMN}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({COLUMN})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id bigserial PRIMARY KEY,
            tenant_id text NOT NULL DEFAULT 'default',
            fact_table varchar(32) NOT NULL,
            fact_id integer NOT NULL,
            source_key varchar(256) NOT NULL,
            distributor_id integer,
            customer_id integer,
            product_id integer NOT NULL,
            transaction_date date,
            invoice_no varchar(128),
            previous_staging_line_id integer,
            previous_import_job_id integer,
            superseded_by_staging_line_id integer NOT NULL,
            superseded_by_import_job_id integer NOT NULL,
            figures jsonb NOT NULL,
            row_json jsonb NOT NULL,
            superseded_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_fact_distributor_line_superseded_table
                CHECK (fact_table IN ('fact_sales_sellout', 'fact_returns'))
        )
        """
    )
    # One record per replaced line and replacing line: re-applying a load never adds a second.
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_distributor_line_superseded_pair
            ON {TABLE} (fact_table, source_key, coalesce(previous_staging_line_id, 0), superseded_by_staging_line_id)
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_fact_dsi_superseded_by_job ON {TABLE} (superseded_by_import_job_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_fact_dsi_superseded_prev_line ON {TABLE} (previous_staging_line_id)")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY cip_pl_select ON {TABLE} FOR SELECT "
        f"USING ({_inline('cip.product_lines', 'cip_product_line_visible')})"
    )
    op.execute(
        f"CREATE POLICY cip_pl_insert ON {TABLE} FOR INSERT "
        f"WITH CHECK ({_inline('cip.editable_product_lines', 'cip_product_line_editable')})"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT ON {TABLE} TO cip;
            GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")

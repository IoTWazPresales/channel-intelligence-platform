"""Customer sell-through stock gap: period grain, in transit, on order, expected position.

Revision ID: 20261014_0037
Revises: 20261014_0036
Create Date: 2026-10-14

N-0110. The customer report's on-hand is the stock position. CIP stores an expected
position beside it and the unit gap. Neither number is rewritten.

- ``period_grain`` (day / week / month), ``period_week`` / ``period_year`` and
  ``week_start_date`` on staging and fact rows. Existing rows keep NULL grain (not
  re-classified). ``week_start_date`` is filled only when the customer's week calendar
  is known.
- ``in_transit_units`` and ``on_order_units`` are stored apart from on-hand.
- ``customer_stock_position`` holds one compared position per customer, product and
  report period. It is derived and recomputed; it never edits fact rows.

Additive; existing rows unchanged.

Idempotent: ``20260801_0001`` create_all already has the columns and
``customer_stock_position``. ``20261006_0024`` may already have created the
``cip_pl_*`` policies on that table.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261014_0037"
down_revision: Union[str, Sequence[str], None] = "20261014_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROW_TABLES = ("import_customer_sellthrough_staging_line", "fact_customer_sellthrough")
_ROW_COLUMNS = (
    ("period_grain", "varchar(8)"),
    ("period_week", "smallint"),
    ("period_year", "smallint"),
    ("week_start_date", "date"),
    ("in_transit_units", "numeric(18, 4)"),
    ("on_order_units", "numeric(18, 4)"),
)


def _add_check_if_missing(table: str, name: str, expression: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = '{name}'
              AND conrelid = 'public.{table}'::regclass
          ) THEN
            ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression});
          END IF;
        END $$;
        """
    )


def _add_policy_if_missing(name: str, statement: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'customer_stock_position'
              AND policyname = '{name}'
          ) THEN
            EXECUTE $policy${statement}$policy$;
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for table in _ROW_TABLES:
        for column, col_type in _ROW_COLUMNS:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}")
        _add_check_if_missing(
            table,
            f"ck_{table}_period_grain"[:63],
            "period_grain IS NULL OR period_grain IN ('day', 'week', 'month')",
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_stock_position (
            id bigserial PRIMARY KEY,
            tenant_id text NOT NULL DEFAULT 'default',
            customer_id integer NOT NULL REFERENCES dim_customer(id) ON DELETE CASCADE,
            product_id integer NOT NULL REFERENCES dim_product(id) ON DELETE CASCADE,
            period_grain varchar(8) NOT NULL,
            period_start_date date NOT NULL,
            period_end_date date NOT NULL,
            period_week smallint,
            period_year smallint,
            report_import_job_id integer REFERENCES import_job(id) ON DELETE SET NULL,
            reported_on_hand numeric(18, 4) NOT NULL,
            units_sold numeric(18, 4) NOT NULL DEFAULT 0,
            in_transit_units numeric(18, 4),
            on_order_units numeric(18, 4),
            previous_period_end_date date,
            previous_on_hand numeric(18, 4),
            receipts_units numeric(18, 4),
            expected_on_hand numeric(18, 4),
            gap_units numeric(18, 4),
            status varchar(16) NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_customer_stock_position_grain CHECK (period_grain IN ('day', 'week', 'month')),
            CONSTRAINT ck_customer_stock_position_status CHECK (status IN ('compared', 'first_report')),
            CONSTRAINT uq_customer_stock_position_period UNIQUE (
                tenant_id, customer_id, product_id, period_grain, period_start_date
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_customer_stock_position_customer_end
            ON customer_stock_position (tenant_id, customer_id, period_end_date)
        """
    )
    # CREATE TABLE IF NOT EXISTS skips these when create_all already built the table.
    _add_check_if_missing(
        "customer_stock_position",
        "ck_customer_stock_position_grain",
        "period_grain IN ('day', 'week', 'month')",
    )
    _add_check_if_missing(
        "customer_stock_position",
        "ck_customer_stock_position_status",
        "status IN ('compared', 'first_report')",
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_customer_stock_position_period'
              AND conrelid = 'public.customer_stock_position'::regclass
          ) THEN
            ALTER TABLE customer_stock_position
              ADD CONSTRAINT uq_customer_stock_position_period
              UNIQUE (tenant_id, customer_id, product_id, period_grain, period_start_date);
          END IF;
        END $$;
        """
    )
    # Same product-line row security as every other product table (20261006_0024, D-0056).
    op.execute("ALTER TABLE customer_stock_position ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE customer_stock_position FORCE ROW LEVEL SECURITY")
    _add_policy_if_missing(
        "cip_pl_select",
        "CREATE POLICY cip_pl_select ON customer_stock_position FOR SELECT "
        "USING (cip_product_id_visible((product_id)::bigint))",
    )
    _add_policy_if_missing(
        "cip_pl_insert",
        "CREATE POLICY cip_pl_insert ON customer_stock_position FOR INSERT "
        "WITH CHECK (cip_product_id_editable((product_id)::bigint))",
    )
    _add_policy_if_missing(
        "cip_pl_update",
        "CREATE POLICY cip_pl_update ON customer_stock_position FOR UPDATE "
        "USING (cip_product_id_editable((product_id)::bigint)) "
        "WITH CHECK (cip_product_id_editable((product_id)::bigint))",
    )
    _add_policy_if_missing(
        "cip_pl_delete",
        "CREATE POLICY cip_pl_delete ON customer_stock_position FOR DELETE "
        "USING (cip_product_id_editable((product_id)::bigint))",
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON customer_stock_position TO cip;
            GRANT USAGE, SELECT ON SEQUENCE customer_stock_position_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customer_stock_position")
    for table in _ROW_TABLES:
        check_name = f"ck_{table}_period_grain"[:63]
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {check_name}")
        for col in (
            "on_order_units",
            "in_transit_units",
            "week_start_date",
            "period_year",
            "period_week",
            "period_grain",
        ):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

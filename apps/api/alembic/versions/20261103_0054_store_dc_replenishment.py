"""Store and DC replenishment: site level, candidates, and the accounts a DC serves.

Revision ID: 20261103_0054
Revises: 20261103_0053
Create Date: 2026-11-03

Level and owner sit beside location type. A distributor owner cannot be saved as a
customer distribution centre. Candidates are not locations. Nothing in this migration
inserts a customer, a distributor, a product, or a location.

NOT APPLIED to cip. Apply on a disposable database.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261103_0054"
down_revision: Union[str, Sequence[str], None] = "20261103_0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_check(name: str, table: str, expression: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
            ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression});
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute("ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS site_level varchar(32)")
    op.execute(
        "ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS site_owner varchar(32) NOT NULL DEFAULT 'customer'"
    )
    op.execute("ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS confirmed_at timestamptz")
    op.execute("ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS confirmed_by text")
    op.execute("ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS latitude numeric(9,6)")
    op.execute("ALTER TABLE customer_location ADD COLUMN IF NOT EXISTS longitude numeric(9,6)")
    _add_check(
        "ck_customer_location_site_level",
        "customer_location",
        "site_level IS NULL OR site_level IN ('distributor_stock', 'customer_dc', 'store', 'other')",
    )
    _add_check(
        "ck_customer_location_site_owner",
        "customer_location",
        "site_owner IN ('customer', 'distributor')",
    )
    _add_check(
        "ck_customer_location_owner_not_dc",
        "customer_location",
        "site_owner <> 'distributor' OR site_level IS DISTINCT FROM 'customer_dc'",
    )
    _add_check(
        "ck_customer_location_latitude",
        "customer_location",
        "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
    )
    _add_check(
        "ck_customer_location_longitude",
        "customer_location",
        "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
    )
    _add_check(
        "ck_customer_location_coords_pair",
        "customer_location",
        "(latitude IS NULL) = (longitude IS NULL)",
    )

    op.execute("ALTER TABLE distributor_location ADD COLUMN IF NOT EXISTS site_level varchar(32)")
    op.execute(
        "ALTER TABLE distributor_location ADD COLUMN IF NOT EXISTS site_owner varchar(32) NOT NULL DEFAULT 'distributor'"
    )
    op.execute("ALTER TABLE distributor_location ADD COLUMN IF NOT EXISTS confirmed_at timestamptz")
    op.execute("ALTER TABLE distributor_location ADD COLUMN IF NOT EXISTS confirmed_by text")
    _add_check(
        "ck_distributor_location_site_level",
        "distributor_location",
        "site_level IS NULL OR site_level IN ('distributor_stock', 'customer_dc', 'store', 'other')",
    )
    _add_check(
        "ck_distributor_location_site_owner",
        "distributor_location",
        "site_owner IN ('customer', 'distributor')",
    )
    _add_check(
        "ck_distributor_location_owner_not_dc",
        "distributor_location",
        "site_owner <> 'distributor' OR site_level IS DISTINCT FROM 'customer_dc'",
    )

    op.execute(
        "ALTER TABLE customer_report_config ADD COLUMN IF NOT EXISTS slow_cover_multiple numeric(8,2)"
    )
    op.execute("ALTER TABLE customer_report_config ADD COLUMN IF NOT EXISTS unsold_weeks numeric(8,2)")
    _add_check(
        "ck_customer_report_config_slow_multiple",
        "customer_report_config",
        "slow_cover_multiple IS NULL OR slow_cover_multiple > 0",
    )
    _add_check(
        "ck_customer_report_config_unsold_weeks",
        "customer_report_config",
        "unsold_weeks IS NULL OR unsold_weeks > 0",
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS site_candidate (
          id serial PRIMARY KEY,
          tenant_id text NOT NULL DEFAULT 'default',
          customer_id integer REFERENCES dim_customer(id) ON DELETE CASCADE,
          distributor_id integer REFERENCES dim_distributor(id) ON DELETE SET NULL,
          location_id integer REFERENCES customer_location(id) ON DELETE SET NULL,
          site_label text NOT NULL,
          site_label_norm text NOT NULL,
          evidence_kind text NOT NULL,
          status text NOT NULL DEFAULT 'open',
          decided_at timestamptz,
          decided_by text,
          evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
          blocked_as_distributor_site boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    _add_check(
        "ck_site_candidate_kind",
        "site_candidate",
        "evidence_kind IN ('pattern', 'stock_behaviour', 'direct_shipment')",
    )
    _add_check(
        "ck_site_candidate_status",
        "site_candidate",
        "status IN ('open', 'confirmed', 'rejected')",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_site_candidate_identity
        ON site_candidate (tenant_id, (COALESCE(customer_id, 0)), site_label_norm)
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_site_candidate_tenant_status ON site_candidate (tenant_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_served_account (
          id serial PRIMARY KEY,
          tenant_id text NOT NULL DEFAULT 'default',
          candidate_id integer NOT NULL REFERENCES site_candidate(id) ON DELETE CASCADE,
          customer_id integer NOT NULL REFERENCES dim_customer(id) ON DELETE CASCADE,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (candidate_id, customer_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dc_served_account_customer ON dc_served_account (tenant_id, customer_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS store_dc_tenant_config (
          tenant_id text PRIMARY KEY,
          lead_time_min_deliveries integer NOT NULL DEFAULT 5,
          dc_name_patterns jsonb NOT NULL DEFAULT '[]'::jsonb,
          stock_behaviour_min_soh numeric(18,4) NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    _add_check(
        "ck_store_dc_min_deliveries",
        "store_dc_tenant_config",
        "lead_time_min_deliveries >= 1 AND lead_time_min_deliveries <= 1000",
    )
    _add_check(
        "ck_store_dc_stock_min_soh",
        "store_dc_tenant_config",
        "stock_behaviour_min_soh > 0",
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dc_served_account")
    op.execute("DROP TABLE IF EXISTS site_candidate")
    op.execute("DROP TABLE IF EXISTS store_dc_tenant_config")
    for name, table in (
        ("ck_customer_report_config_unsold_weeks", "customer_report_config"),
        ("ck_customer_report_config_slow_multiple", "customer_report_config"),
        ("ck_distributor_location_owner_not_dc", "distributor_location"),
        ("ck_distributor_location_site_owner", "distributor_location"),
        ("ck_distributor_location_site_level", "distributor_location"),
        ("ck_customer_location_coords_pair", "customer_location"),
        ("ck_customer_location_longitude", "customer_location"),
        ("ck_customer_location_latitude", "customer_location"),
        ("ck_customer_location_owner_not_dc", "customer_location"),
        ("ck_customer_location_site_owner", "customer_location"),
        ("ck_customer_location_site_level", "customer_location"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute("ALTER TABLE customer_report_config DROP COLUMN IF EXISTS unsold_weeks")
    op.execute("ALTER TABLE customer_report_config DROP COLUMN IF EXISTS slow_cover_multiple")
    op.execute("ALTER TABLE distributor_location DROP COLUMN IF EXISTS confirmed_by")
    op.execute("ALTER TABLE distributor_location DROP COLUMN IF EXISTS confirmed_at")
    op.execute("ALTER TABLE distributor_location DROP COLUMN IF EXISTS site_owner")
    op.execute("ALTER TABLE distributor_location DROP COLUMN IF EXISTS site_level")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS longitude")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS latitude")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS confirmed_by")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS confirmed_at")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS site_owner")
    op.execute("ALTER TABLE customer_location DROP COLUMN IF EXISTS site_level")

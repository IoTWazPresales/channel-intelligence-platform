"""M5c option 1 (D-0149): tenant_id on source_definition and steward alias tables.

Revision ID: 20261103_0052
Revises: 20261102_0051
Create Date: 2026-11-03

Scopes column_mapping_memory and approved alias rows per tenant. Backfill from the related
master's tenant_id where available, else ``default``. Unique keys include tenant_id.

NOT applied to production ``cip`` by this agent run.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261103_0052"
down_revision: Union[str, Sequence[str], None] = "20261102_0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES_MASTER_BACKFILL: tuple[tuple[str, str, str], ...] = (
    ("customer_source_token_alias", "customer_id", "dim_customer"),
    ("distributor_source_token_alias", "distributor_id", "dim_distributor"),
    ("product_alias", "product_id", "dim_product"),
    ("customer_article_alias", "customer_id", "dim_customer"),
)

_TABLES_DEFAULT_ONLY: tuple[str, ...] = (
    "channel_source_token_alias",
    "region_source_token_alias",
)


def _add_tenant_column(table: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table}
          ADD COLUMN IF NOT EXISTS tenant_id TEXT NULL
        """
    )


def _backfill_from_master(table: str, fk_col: str, master_table: str) -> None:
    op.execute(
        f"""
        UPDATE {table} AS t
        SET tenant_id = COALESCE(m.tenant_id, 'default')
        FROM {master_table} AS m
        WHERE t.{fk_col} = m.id
          AND t.tenant_id IS NULL
        """
    )
    op.execute(f"UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL")


def _finalize_tenant_column(table: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table}
          ALTER COLUMN tenant_id SET NOT NULL,
          ALTER COLUMN tenant_id SET DEFAULT 'default'
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_{table}_tenant_id'
          ) THEN
            ALTER TABLE {table}
              ADD CONSTRAINT fk_{table}_tenant_id
              FOREIGN KEY (tenant_id) REFERENCES tenant(id);
          END IF;
        END $$;
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)")


def upgrade() -> None:
    # --- source_definition ---
    _add_tenant_column("source_definition")
    op.execute(
        """
        UPDATE source_definition sd
        SET tenant_id = COALESCE(
          (
            SELECT ij.tenant_id
            FROM import_job ij
            WHERE ij.source_id = sd.id
            GROUP BY ij.tenant_id
            ORDER BY COUNT(*) DESC
            LIMIT 1
          ),
          'default'
        )
        WHERE sd.tenant_id IS NULL
        """
    )
    op.execute("UPDATE source_definition SET tenant_id = 'default' WHERE tenant_id IS NULL")
    _finalize_tenant_column("source_definition")
    op.execute("ALTER TABLE source_definition DROP CONSTRAINT IF EXISTS source_definition_code_key")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_source_definition_tenant_code
          ON source_definition (tenant_id, code)
        """
    )

    for table, fk_col, master in _TABLES_MASTER_BACKFILL:
        _add_tenant_column(table)
        _backfill_from_master(table, fk_col, master)
        _finalize_tenant_column(table)

    for table in _TABLES_DEFAULT_ONLY:
        _add_tenant_column(table)
        op.execute(f"UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL")
        _finalize_tenant_column(table)

    # --- approved alias unique indexes (include tenant_id) ---
    op.execute("DROP INDEX IF EXISTS uq_cust_src_token_alias_approved_scope")
    op.execute("DROP INDEX IF EXISTS uq_dist_src_token_alias_approved_scope")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cust_src_token_alias_approved_scope
        ON customer_source_token_alias (
            tenant_id,
            normalized_token,
            COALESCE(source_definition_id, -1),
            COALESCE(distributor_id, -1)
        )
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_dist_src_token_alias_approved_scope
        ON distributor_source_token_alias (
            tenant_id,
            normalized_token,
            COALESCE(source_definition_id, -1)
        )
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_src_token_alias_approved_scope
        ON channel_source_token_alias (
            tenant_id,
            normalized_token,
            COALESCE(source_definition_id, -1),
            channel_id
        )
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_region_src_token_alias_approved_scope
        ON region_source_token_alias (
            tenant_id,
            normalized_token,
            COALESCE(source_definition_id, -1),
            region_id
        )
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_product_alias_tenant_value_kind
        ON product_alias (tenant_id, lower(alias_value), alias_kind)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_product_alias_tenant_value_kind")
    op.execute("DROP INDEX IF EXISTS uq_region_src_token_alias_approved_scope")
    op.execute("DROP INDEX IF EXISTS uq_channel_src_token_alias_approved_scope")
    op.execute("DROP INDEX IF EXISTS uq_dist_src_token_alias_approved_scope")
    op.execute("DROP INDEX IF EXISTS uq_cust_src_token_alias_approved_scope")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dist_src_token_alias_approved_scope
        ON distributor_source_token_alias (
            normalized_token,
            COALESCE(source_definition_id, -1)
        )
        WHERE status = 'approved'
        """
    )
    op.execute(
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

    op.execute("DROP INDEX IF EXISTS uq_source_definition_tenant_code")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM source_definition
            GROUP BY code HAVING COUNT(DISTINCT tenant_id) > 1
          ) THEN
            RAISE EXCEPTION 'Same source_definition code on multiple tenants: cannot restore global code unique';
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS source_definition_code_key
          ON source_definition (code)
        """
    )

    for table in (
        "region_source_token_alias",
        "channel_source_token_alias",
        "customer_article_alias",
        "product_alias",
        "distributor_source_token_alias",
        "customer_source_token_alias",
        "source_definition",
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_tenant_id")
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")

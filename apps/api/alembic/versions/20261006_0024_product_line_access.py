"""Product-line access and column-set grain.

Revision ID: 20261006_0024
Revises: 20260924_0023
Create Date: 2026-10-06

Adds user product-line grants and the tenant column-set grain. Does not add a
unique index on dim_product.ean. Duplicate EAN stays a flag.

Row security hides product rows from a signed-in user who was not assigned
that line. An unset database setting (workers, migrations) still sees every row.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261006_0024"
down_revision: Union[str, Sequence[str], None] = "20260924_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_product_line_access (
            id bigserial PRIMARY KEY,
            tenant_id text NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            user_id bigint NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            product_line text NOT NULL,
            can_edit boolean NOT NULL DEFAULT false,
            CONSTRAINT uq_user_product_line_access UNIQUE (user_id, product_line)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_column_grain (
            tenant_id text PRIMARY KEY REFERENCES tenant(id) ON DELETE CASCADE,
            grain text NOT NULL DEFAULT 'product_line',
            CONSTRAINT tenant_column_grain_not_blank CHECK (btrim(grain) <> '')
        )
        """
    )
    op.execute(
        """
        INSERT INTO tenant_column_grain (tenant_id, grain)
        SELECT id, 'product_line' FROM tenant
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cip_product_line_visible(line text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
          SELECT current_setting('cip.product_lines', true) IS NULL
              OR current_setting('cip.product_lines', true) = '*'
              OR (
                line IS NOT NULL
                AND line = ANY (string_to_array(current_setting('cip.product_lines', true), ','))
              );
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cip_product_line_editable(line text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
          SELECT current_setting('cip.editable_product_lines', true) IS NULL
              OR current_setting('cip.editable_product_lines', true) = '*'
              OR (
                line IS NOT NULL
                AND line = ANY (string_to_array(current_setting('cip.editable_product_lines', true), ','))
              );
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cip_product_id_visible(pid bigint)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT pid IS NULL
              OR EXISTS (
                SELECT 1 FROM dim_product p
                WHERE p.id = pid AND cip_product_line_visible(p.product_line)
              );
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cip_product_id_editable(pid bigint)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT pid IS NULL
              OR EXISTS (
                SELECT 1 FROM dim_product p
                WHERE p.id = pid AND cip_product_line_editable(p.product_line)
              );
        $$
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION cip_product_line_visible(text) TO PUBLIC;
        GRANT EXECUTE ON FUNCTION cip_product_line_editable(text) TO PUBLIC;
        GRANT EXECUTE ON FUNCTION cip_product_id_visible(bigint) TO PUBLIC;
        GRANT EXECUTE ON FUNCTION cip_product_id_editable(bigint) TO PUBLIC;
        GRANT SELECT, INSERT, UPDATE, DELETE ON user_product_line_access TO cip;
        GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_column_grain TO cip;
        GRANT USAGE, SELECT ON SEQUENCE user_product_line_access_id_seq TO cip;
        """
    )
    op.execute(
        """
        ALTER TABLE dim_product ENABLE ROW LEVEL SECURITY;
        ALTER TABLE dim_product FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS cip_pl_select ON dim_product;
        DROP POLICY IF EXISTS cip_pl_insert ON dim_product;
        DROP POLICY IF EXISTS cip_pl_update ON dim_product;
        DROP POLICY IF EXISTS cip_pl_delete ON dim_product;
        CREATE POLICY cip_pl_select ON dim_product
          FOR SELECT USING (cip_product_line_visible(product_line));
        CREATE POLICY cip_pl_insert ON dim_product
          FOR INSERT WITH CHECK (cip_product_line_editable(product_line));
        CREATE POLICY cip_pl_update ON dim_product
          FOR UPDATE
          USING (cip_product_line_editable(product_line))
          WITH CHECK (cip_product_line_editable(product_line));
        CREATE POLICY cip_pl_delete ON dim_product
          FOR DELETE USING (cip_product_line_editable(product_line));
        """
    )
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT c.table_name,
                   COALESCE(
                     MAX(c.column_name) FILTER (WHERE c.column_name = 'product_id'),
                     MAX(c.column_name) FILTER (WHERE c.column_name = 'canonical_product_id')
                   ) AS column_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name IN ('product_id', 'canonical_product_id')
              AND c.data_type IN ('integer', 'bigint', 'smallint')
              AND c.table_name <> 'dim_product'
            GROUP BY c.table_name
          LOOP
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', r.table_name);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_select ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_insert ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_update ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_delete ON %I', r.table_name);
            EXECUTE format(
              'CREATE POLICY cip_pl_select ON %I FOR SELECT USING (cip_product_id_visible((%I)::bigint))',
              r.table_name, r.column_name
            );
            EXECUTE format(
              'CREATE POLICY cip_pl_insert ON %I FOR INSERT WITH CHECK (cip_product_id_editable((%I)::bigint))',
              r.table_name, r.column_name
            );
            EXECUTE format(
              'CREATE POLICY cip_pl_update ON %I FOR UPDATE USING (cip_product_id_editable((%I)::bigint)) WITH CHECK (cip_product_id_editable((%I)::bigint))',
              r.table_name, r.column_name, r.column_name
            );
            EXECUTE format(
              'CREATE POLICY cip_pl_delete ON %I FOR DELETE USING (cip_product_id_editable((%I)::bigint))',
              r.table_name, r.column_name
            );
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS cip_pl_select ON dim_product;
        DROP POLICY IF EXISTS cip_pl_insert ON dim_product;
        DROP POLICY IF EXISTS cip_pl_update ON dim_product;
        DROP POLICY IF EXISTS cip_pl_delete ON dim_product;
        ALTER TABLE dim_product NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE dim_product DISABLE ROW LEVEL SECURITY;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name IN ('product_id', 'canonical_product_id')
          LOOP
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_select ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_insert ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_update ON %I', r.table_name);
            EXECUTE format('DROP POLICY IF EXISTS cip_pl_delete ON %I', r.table_name);
            EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', r.table_name);
            EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', r.table_name);
          END LOOP;
        END $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS cip_product_id_editable(bigint)")
    op.execute("DROP FUNCTION IF EXISTS cip_product_id_visible(bigint)")
    op.execute("DROP FUNCTION IF EXISTS cip_product_line_editable(text)")
    op.execute("DROP FUNCTION IF EXISTS cip_product_line_visible(text)")
    op.execute("DROP TABLE IF EXISTS tenant_column_grain")
    op.execute("DROP TABLE IF EXISTS user_product_line_access")

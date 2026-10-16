"""Customer sell-through column layouts, and a soft-hide flag on sources.

Revision ID: 20261016_0043
Revises: 20261016_0042
Create Date: 2026-10-16

N-0111 (Warren 2026-10-16): a sell-through upload picks a reporting customer, not a source. The
only per-customer configuration is the column layout, saved the first time a header set is mapped.
``customer_sellthrough_layout`` holds it (one row per customer and header set). Test and build
sources are hidden with ``source_definition.is_hidden`` (soft; nothing is deleted).

Additive: one new table, one new column with a default; no existing row changes. Needs the table
owner (on cip: ``postgres``), so run it with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0043"
down_revision: Union[str, Sequence[str], None] = "20261016_0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "customer_sellthrough_layout"


def upgrade() -> None:
    op.execute("ALTER TABLE source_definition ADD COLUMN IF NOT EXISTS is_hidden boolean NOT NULL DEFAULT false")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id serial PRIMARY KEY,
            customer_id integer NOT NULL REFERENCES dim_customer(id),
            name varchar(256) NOT NULL,
            header_signature varchar(64) NOT NULL,
            headers jsonb NOT NULL DEFAULT '[]'::jsonb,
            field_mapping jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            report_structure_type varchar(32),
            origin varchar(32) NOT NULL DEFAULT 'upload',
            origin_source_id integer REFERENCES source_definition(id),
            origin_import_job_id integer REFERENCES import_job(id) ON DELETE SET NULL,
            is_hidden boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_cst_layout_customer_signature UNIQUE (customer_id, header_signature)
        )
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_customer_id ON {TABLE} (customer_id)")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT, UPDATE ON {TABLE} TO cip;
            GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute("ALTER TABLE source_definition DROP COLUMN IF EXISTS is_hidden")

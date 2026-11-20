"""Discovery V2: customer web sites, and listing-link queue rows that need a product.

Revision ID: 20261121_0065
Revises: 20261120_0064
Create Date: 2026-11-21

Adds ``customer_web_site`` (the customer-to-domain association and the site-candidate steward
queue; ``status = 'proposed'`` is the queue) and lets ``listing_link_queue.product_id`` be NULL
for a listing that has no product yet (a steward picks the product). A check keeps one target on
every row, and a partial unique index allows one open row per listing with no product.

No rows are inserted and nothing is seeded. Idempotent: the table and indexes are created only
when missing, ``DROP NOT NULL`` is a no-op when already nullable, and the check constraint is
added only when absent. Needs the table owner; on ``cip`` run with DATABASE_URL_SYNC_MIGRATE set
to the owner connection, only with Warren's approval and after a backup. The app role ``cip`` is
granted the table commands only when that role exists.

Downgrade deletes the ``listing_link_queue`` rows that have no product (an open "needs a product"
item is lost; that loss is documented here), restores NOT NULL, drops the check, the index and
the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261121_0065"
down_revision: str | Sequence[str] | None = "20261120_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_web_site (
            id serial PRIMARY KEY,
            tenant_id text NOT NULL,
            customer_id integer NOT NULL REFERENCES dim_customer(id),
            domain varchar(253) NOT NULL,
            site_id integer NULL REFERENCES listing_site(id) ON DELETE SET NULL,
            status varchar(16) NOT NULL,
            source varchar(16) NOT NULL,
            evidence jsonb NOT NULL DEFAULT '{}',
            preview_id varchar(36),
            decided_by varchar(256),
            decided_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_customer_web_site_status CHECK (status IN ('proposed', 'confirmed', 'rejected')),
            CONSTRAINT ck_customer_web_site_source CHECK (source IN ('auto', 'steward', 'user')),
            CONSTRAINT uq_customer_web_site_tenant_customer_domain UNIQUE (tenant_id, customer_id, domain)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_web_site_tenant_status "
        "ON customer_web_site (tenant_id, status)"
    )
    op.execute("ALTER TABLE listing_link_queue ALTER COLUMN product_id DROP NOT NULL")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_listing_link_queue_target'
              AND conrelid = 'listing_link_queue'::regclass
          ) THEN
            ALTER TABLE listing_link_queue
              ADD CONSTRAINT ck_listing_link_queue_target
              CHECK (product_id IS NOT NULL OR listing_id IS NOT NULL);
          END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_link_queue_open_listing "
        "ON listing_link_queue (listing_id) WHERE status = 'open' AND product_id IS NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON customer_web_site TO cip;
            GRANT USAGE, SELECT ON SEQUENCE customer_web_site_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM listing_link_queue WHERE product_id IS NULL")
    op.execute("DROP INDEX IF EXISTS uq_listing_link_queue_open_listing")
    op.execute("ALTER TABLE listing_link_queue DROP CONSTRAINT IF EXISTS ck_listing_link_queue_target")
    op.execute("ALTER TABLE listing_link_queue ALTER COLUMN product_id SET NOT NULL")
    op.execute("DROP TABLE IF EXISTS customer_web_site")

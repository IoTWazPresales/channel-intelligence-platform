"""Listing sites, learned links, offers, and each customer's seller identity are tenant data.

Revision ID: 20261103_0053
Revises: 20261103_0052
Create Date: 2026-11-03

``20261103_0052`` is the My accounts table on the parent branch. This revision follows it so
the branch has one Alembic head. A merge that needs a different parent can change
``down_revision``; the statements below do not depend on ``user_customer_account``.

``listing_site``: one row per tenant and site. ``site_key`` is the value already stored in
``customer_listing.marketplace``. The page reader (``adapter_key``), the product link pattern, the
search pattern, the data endpoint pattern, the page-id pattern, the seller name the site shows for its
own stock and the request spacing are columns, edited in the app. Nothing in code names a site.

``listing_site_seller``: which customer sells on which site, with that customer's own seller names
and seller ids on the site. The buy box is the customer's own when its seller is one of these.

Backfill: a site row per distinct ``marketplace`` already on ``customer_listing`` or
``cst_listing_seed`` (tenant from the customer), with the key as its display name and no reader. The
link patterns and sellers that used to be code constants are not copied: a site with no reader is
"not configured" and is not fetched until a steward fills it in. Existing rows are not rewritten.

Row security: enabled and forced; permissive policies (tenant scoping is the ``tenant_id`` column,
applied by the API). Sites are deactivated, never deleted (no DELETE policy); a customer's seller
row may be deleted.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261103_0053"
down_revision: Union[str, Sequence[str], None] = "20261103_0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _policies(table: str, commands: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for command in commands:
        name = f"cip_{table}_{command.lower()}"
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        if command == "INSERT":
            op.execute(f"CREATE POLICY {name} ON {table} FOR INSERT WITH CHECK (true)")
        elif command == "UPDATE":
            op.execute(f"CREATE POLICY {name} ON {table} FOR UPDATE USING (true) WITH CHECK (true)")
        else:
            op.execute(f"CREATE POLICY {name} ON {table} FOR {command} USING (true)")
    grants = ", ".join(commands)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT {grants} ON {table} TO cip;
            GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def _sites() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_site (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            site_key varchar(32) NOT NULL,
            display_name varchar(128) NOT NULL,
            adapter_key varchar(32),
            product_url_pattern text,
            page_id_pattern text,
            search_url_pattern text,
            details_url_pattern text,
            first_party_seller varchar(256),
            rate_limit_seconds numeric(8, 2),
            is_active boolean NOT NULL DEFAULT true,
            updated_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_listing_site PRIMARY KEY (id),
            CONSTRAINT uq_listing_site_tenant_key UNIQUE (tenant_id, site_key)
        )
        """
    )
    _policies("listing_site", ("SELECT", "INSERT", "UPDATE"))
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_site_seller (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            site_id integer NOT NULL REFERENCES listing_site (id) ON DELETE CASCADE,
            customer_id integer NOT NULL REFERENCES dim_customer (id),
            seller_names jsonb NOT NULL DEFAULT '[]'::jsonb,
            seller_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            updated_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_listing_site_seller PRIMARY KEY (id),
            CONSTRAINT uq_listing_site_seller_site_customer UNIQUE (site_id, customer_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_listing_site_seller_customer ON listing_site_seller (customer_id)")
    _policies("listing_site_seller", ("SELECT", "INSERT", "UPDATE", "DELETE"))


def _backfill_sites() -> None:
    op.execute(
        """
        INSERT INTO listing_site (tenant_id, site_key, display_name)
        SELECT DISTINCT coalesce(c.tenant_id, 'default'), src.marketplace, src.marketplace
        FROM (
            SELECT customer_id, lower(trim(marketplace)) AS marketplace FROM customer_listing
            UNION
            SELECT customer_id, lower(trim(marketplace)) AS marketplace FROM cst_listing_seed
        ) src
        JOIN dim_customer c ON c.id = src.customer_id
        WHERE src.marketplace <> ''
        ON CONFLICT ON CONSTRAINT uq_listing_site_tenant_key DO NOTHING
        """
    )


def _links_offers() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_link (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            site_id integer NOT NULL REFERENCES listing_site (id) ON DELETE CASCADE,
            product_id integer NOT NULL REFERENCES dim_product (id),
            url text NOT NULL,
            status varchar(16) NOT NULL,
            evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
            decided_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_listing_link PRIMARY KEY (id),
            CONSTRAINT uq_listing_link_site_product_url UNIQUE (site_id, product_id, url),
            CONSTRAINT ck_listing_link_status CHECK (status IN ('confirmed', 'rejected', 'stale'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_link_one_confirmed
        ON listing_link (site_id, product_id)
        WHERE status = 'confirmed'
        """
    )
    _policies("listing_link", ("SELECT", "INSERT", "UPDATE"))
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_link_queue (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            site_id integer NOT NULL REFERENCES listing_site (id) ON DELETE CASCADE,
            product_id integer NOT NULL REFERENCES dim_product (id),
            customer_id integer REFERENCES dim_customer (id),
            listing_id integer REFERENCES customer_listing (id) ON DELETE SET NULL,
            reason varchar(32) NOT NULL,
            candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'open',
            evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_listing_link_queue PRIMARY KEY (id),
            CONSTRAINT ck_listing_link_queue_status CHECK (status IN ('open', 'confirmed', 'rejected', 'not_on_site'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_link_queue_open
        ON listing_link_queue (site_id, product_id)
        WHERE status = 'open'
        """
    )
    _policies("listing_link_queue", ("SELECT", "INSERT", "UPDATE"))
    op.execute(
        """
        ALTER TABLE listing_observation
            ADD COLUMN IF NOT EXISTS buy_box_seller varchar(256),
            ADD COLUMN IF NOT EXISTS buy_box_own boolean,
            ADD COLUMN IF NOT EXISTS offer_count integer
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_offer (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            observation_id integer NOT NULL REFERENCES listing_observation (id) ON DELETE CASCADE,
            listing_id integer NOT NULL REFERENCES customer_listing (id) ON DELETE CASCADE,
            seller_name varchar(256),
            seller_id varchar(128),
            price numeric(18, 4),
            availability varchar(64),
            is_buy_box boolean NOT NULL DEFAULT false,
            is_own_seller boolean,
            offer_ref varchar(128),
            condition varchar(64),
            captured_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_listing_offer PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_listing_offer_observation ON listing_offer (observation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_listing_offer_listing ON listing_offer (listing_id)")
    _policies("listing_offer", ("SELECT", "INSERT"))


def upgrade() -> None:
    _sites()
    _backfill_sites()
    _links_offers()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS listing_offer")
    op.execute("ALTER TABLE listing_observation DROP COLUMN IF EXISTS offer_count")
    op.execute("ALTER TABLE listing_observation DROP COLUMN IF EXISTS buy_box_own")
    op.execute("ALTER TABLE listing_observation DROP COLUMN IF EXISTS buy_box_seller")
    op.execute("DROP TABLE IF EXISTS listing_link_queue")
    op.execute("DROP TABLE IF EXISTS listing_link")
    op.execute("DROP TABLE IF EXISTS listing_site_seller")
    op.execute("DROP TABLE IF EXISTS listing_site")

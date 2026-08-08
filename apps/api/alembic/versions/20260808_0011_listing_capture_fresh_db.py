"""Listing Capture (LC-U1) tables for fresh DBs only — AUTHOR ONLY, do not apply.

Revision ID: 20260808_0011
Revises: 20260807_0010
Create Date: 2026-08-08

IMPORTANT — do not run `alembic upgrade` with this revision without Warren's explicit
approval. `customer_listing` and `listing_observation` already exist on the `cip`
dev database (created ad hoc from legacy revision
`apps/api/alembic/versions_legacy/20260709_0069_listing_capture_v0.py`, which sits
outside the live `versions/` chain). This revision exists so a **fresh** database
built from `versions/` alone (no `versions_legacy/` replay) ends up with the same
tables — P5 live-fetch code (`listing_capture_poll_listings_task`) depends on them.

Uses raw SQL with `IF NOT EXISTS` throughout so it is a safe no-op against `cip`
(tables already present) and only does real work on a genuinely fresh database.
Column set is copied verbatim from the legacy 0069 revision — do not drift.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260808_0011"
down_revision: Union[str, Sequence[str], None] = "20260807_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_listing (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES dim_customer (id),
            product_id INTEGER NULL REFERENCES dim_product (id),
            url VARCHAR(1024) NOT NULL,
            marketplace VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            source VARCHAR(32) NOT NULL DEFAULT 'manual',
            registered_by VARCHAR(128) NULL,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status_observed_at TIMESTAMPTZ NULL,
            external_id VARCHAR(128) NULL,
            notes TEXT NULL,
            meta_json JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_customer_listing_customer_url UNIQUE (customer_id, url)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_listing_customer_id "
        "ON customer_listing (customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_listing_product_id "
        "ON customer_listing (product_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_listing_marketplace "
        "ON customer_listing (marketplace)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_observation (
            id SERIAL PRIMARY KEY,
            listing_id INTEGER NOT NULL REFERENCES customer_listing (id),
            fetched_at TIMESTAMPTZ NOT NULL,
            http_status INTEGER NULL,
            raw_snapshot BYTEA NULL,
            parser_version VARCHAR(32) NOT NULL,
            extracted_price NUMERIC(18, 4) NULL,
            extracted_availability VARCHAR(64) NULL,
            extracted_promo_badge VARCHAR(128) NULL,
            parse_status VARCHAR(32) NOT NULL DEFAULT 'ok',
            parse_flags JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listing_observation_listing_id "
        "ON listing_observation (listing_id)"
    )


def downgrade() -> None:
    # Fresh-DB-only revision — downgrade is a no-op to avoid dropping tables that
    # predate this revision on `cip` (created via versions_legacy/20260709_0069).
    pass

"""Dated customer_article_alias eras + btree_gist exclusion.

Revision ID: 20260811_0012
Revises: 20260808_0011
Create Date: 2026-08-11

Adds valid_from / valid_to (half-open [from, to), NULL = ±infinity).
Drops uq_customer_article_alias_customer_article.
Adds EXCLUDE constraint so confirmed/active eras for the same
(customer, article) cannot overlap.

Warren approved apply on cip 2026-08-11 (Unit 5 dated-alias arc).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260811_0012"
down_revision: Union[str, Sequence[str], None] = "20260808_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE customer_article_alias
          ADD COLUMN IF NOT EXISTS valid_from DATE NULL,
          ADD COLUMN IF NOT EXISTS valid_to DATE NULL
        """
    )
    op.execute(
        """
        ALTER TABLE customer_article_alias
          DROP CONSTRAINT IF EXISTS uq_customer_article_alias_customer_article
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ex_customer_article_alias_confirmed_eras'
          ) THEN
            ALTER TABLE customer_article_alias
              ADD CONSTRAINT ex_customer_article_alias_confirmed_eras
              EXCLUDE USING gist (
                customer_id WITH =,
                article_no_normalized WITH =,
                daterange(valid_from, valid_to, '[)') WITH &&
              )
              WHERE (status IN ('confirmed', 'active'));
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_customer_article_alias_customer_article_status
          ON customer_article_alias (customer_id, article_no_normalized, status)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE customer_article_alias "
        "DROP CONSTRAINT IF EXISTS ex_customer_article_alias_confirmed_eras"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_customer_article_alias_customer_article_status"
    )
    # Restore unique only if no duplicate (customer, article) remain.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM (
              SELECT customer_id, article_no_normalized
              FROM customer_article_alias
              GROUP BY 1, 2 HAVING count(*) > 1
            ) d
          ) THEN
            ALTER TABLE customer_article_alias
              ADD CONSTRAINT uq_customer_article_alias_customer_article
              UNIQUE (customer_id, article_no_normalized);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE customer_article_alias
          DROP COLUMN IF EXISTS valid_from,
          DROP COLUMN IF EXISTS valid_to
        """
    )

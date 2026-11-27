"""Drop column defaults that implied a VAT rate, margins or a currency.

Revision ID: 20261127_0067
Revises: 20261123_0066
Create Date: 2026-11-27

VAT, the customer/distributor margins and rebate, and the currency are tenant settings (tenant
profile ``vat_rate_pct`` / ``vat_rate_by_country``, ``profit_reservation_margins`` and
``currency_code``). A column default would fill them silently on any insert that leaves them
out, so these defaults are dropped:

- ``commercial_sku_assumption.vat_rate_pct``
- ``commercial_customer_term.customer_margin_pct`` and ``customer_rebate_pct``
- ``commercial_distributor_term.distributor_margin_pct``
- ``cpor_case.currency_code``
- ``cpor_payment_evidence.currency_code``
- ``fx_daily_rate.quote_pair``

Every column stays NOT NULL, so an insert without a value now fails instead of storing an
assumed one. Stored rows are not changed. ``ALTER COLUMN ... DROP DEFAULT`` is a no-op when the
column has no default (databases built from the 0001 baseline never had these server defaults),
and each table is altered only when it exists. Needs the table owner; on ``cip`` run with
DATABASE_URL_SYNC_MIGRATE set to the owner connection, only with Warren's approval.

Downgrade puts back the defaults the legacy chain and 0013/0021 created.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261127_0067"
down_revision: str | Sequence[str] | None = "20261123_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("commercial_sku_assumption", "vat_rate_pct", "0.15"),
    ("commercial_customer_term", "customer_margin_pct", "0.12"),
    ("commercial_customer_term", "customer_rebate_pct", "0.03"),
    ("commercial_distributor_term", "distributor_margin_pct", "0.08"),
    ("cpor_case", "currency_code", "'ZAR'"),
    ("cpor_payment_evidence", "currency_code", "'ZAR'"),
    ("fx_daily_rate", "quote_pair", "'USDZAR'"),
)


def _alter_if_present(table: str, column: str, action: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{column}'
          ) THEN
            ALTER TABLE public.{table} ALTER COLUMN {column} {action};
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for table, column, _previous in _COLUMNS:
        _alter_if_present(table, column, "DROP DEFAULT")


def downgrade() -> None:
    for table, column, previous in _COLUMNS:
        _alter_if_present(table, column, f"SET DEFAULT {previous}")

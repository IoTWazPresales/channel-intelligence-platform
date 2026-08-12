"""CPOR payment / credit-note evidence tables.

Revision ID: 20260812_0013
Revises: 20260811_0012
Create Date: 2026-08-12

Generic settlement evidence (not Ken-shaped schema). Mapping profiles remap
tenant workbooks onto canonical payment fields. Case status from file is
evidence-only — does not overwrite cpor_case.status.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260812_0013"
down_revision: Union[str, Sequence[str], None] = "20260811_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cpor_payment_mapping_profile (
          id SERIAL PRIMARY KEY,
          profile_code VARCHAR(64) NOT NULL,
          display_name VARCHAR(256) NOT NULL,
          header_row_index INTEGER NOT NULL DEFAULT 1,
          sheet_roles_json JSONB NOT NULL,
          column_map_json JSONB NOT NULL,
          value_maps_json JSONB NOT NULL,
          is_default BOOLEAN NOT NULL DEFAULT FALSE,
          notes TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_cpor_payment_mapping_profile_code UNIQUE (profile_code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS import_cpor_payment_staging_line (
          id SERIAL PRIMARY KEY,
          import_job_id INTEGER NOT NULL REFERENCES import_job(id) ON DELETE CASCADE,
          source_key VARCHAR(512) NOT NULL,
          source_row_number INTEGER NOT NULL,
          sheet_name VARCHAR(128) NOT NULL,
          external_case_code VARCHAR(64) NOT NULL,
          credit_note_id VARCHAR(128) NULL,
          case_status_raw VARCHAR(64) NULL,
          payment_status_raw VARCHAR(64) NULL,
          payment_status VARCHAR(64) NULL,
          payment_date DATE NULL,
          amount NUMERIC(18, 4) NULL,
          currency_code VARCHAR(8) NULL,
          customer_token VARCHAR(256) NULL,
          distributor_token VARCHAR(256) NULL,
          description TEXT NULL,
          window_start DATE NULL,
          window_end DATE NULL,
          promotion_type_raw VARCHAR(128) NULL,
          resolved_customer_id INTEGER NULL REFERENCES dim_customer(id),
          resolved_distributor_id INTEGER NULL REFERENCES dim_distributor(id),
          linked_case_id INTEGER NULL REFERENCES cpor_case(id),
          create_shell_case BOOLEAN NOT NULL DEFAULT FALSE,
          skip_apply BOOLEAN NOT NULL DEFAULT FALSE,
          flags_json JSONB NULL,
          raw_source_row JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_import_cpor_payment_staging_source_key UNIQUE (source_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_import_cpor_payment_staging_job
          ON import_cpor_payment_staging_line (import_job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_import_cpor_payment_staging_case_code
          ON import_cpor_payment_staging_line (external_case_code)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cpor_payment_evidence (
          id SERIAL PRIMARY KEY,
          tenant_id TEXT NOT NULL DEFAULT 'default',
          source_key VARCHAR(512) NOT NULL,
          import_job_id INTEGER NULL REFERENCES import_job(id) ON DELETE SET NULL,
          external_case_code VARCHAR(64) NOT NULL,
          credit_note_id VARCHAR(128) NULL,
          case_status_raw VARCHAR(64) NULL,
          payment_status_raw VARCHAR(64) NULL,
          payment_status VARCHAR(64) NULL,
          payment_date DATE NULL,
          amount NUMERIC(18, 4) NULL,
          currency_code VARCHAR(8) NOT NULL DEFAULT 'ZAR',
          customer_token VARCHAR(256) NULL,
          distributor_token VARCHAR(256) NULL,
          description TEXT NULL,
          customer_id INTEGER NULL REFERENCES dim_customer(id),
          distributor_id INTEGER NULL REFERENCES dim_distributor(id),
          case_id INTEGER NULL REFERENCES cpor_case(id),
          evidence_json JSONB NULL,
          raw_source_row JSONB NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_cpor_payment_evidence_source_key UNIQUE (source_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cpor_payment_evidence_tenant
          ON cpor_payment_evidence (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cpor_payment_evidence_case
          ON cpor_payment_evidence (case_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cpor_payment_evidence_case_code
          ON cpor_payment_evidence (external_case_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cpor_payment_evidence_payment_status
          ON cpor_payment_evidence (payment_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cpor_payment_evidence")
    op.execute("DROP TABLE IF EXISTS import_cpor_payment_staging_line")
    op.execute("DROP TABLE IF EXISTS cpor_payment_mapping_profile")

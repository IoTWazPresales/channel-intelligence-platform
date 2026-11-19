"""Customer campaign / pillar calendars: mapping profile and calendar events (final wave d).

Revision ID: 20261118_0063
Revises: 20261113_0062
Create Date: 2026-11-18

``customer_calendar_mapping_profile``: one row per tenant and profile code, the same shape as the
CPOR payment-evidence and historical-import profiles (header row, header aliases per field, kind
value map). ``customer_calendar_event``: one row per campaign / pillar / other event on a customer's
own calendar, with the file and upload that brought it in. An upload replaces its own earlier
events per customer, so apply is idempotent.

Row security is enabled and forced, with transaction-local tenant context bound by the calendar
service. Unset context denies access. Grants follow the listing-site pattern. The profile may be
edited and deleted; events are inserted and deleted (replace), never updated. The app role
``cip`` is granted the same commands and the id sequences, only when that role exists.

Idempotent: tables, indexes and policies are created only when missing. Downgrade drops both
tables (events first). Needs the table owner; on ``cip`` run it with DATABASE_URL_SYNC_MIGRATE
set to the owner connection, only with Warren's approval and after a backup.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261118_0063"
down_revision: str | Sequence[str] | None = "20261113_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE = "customer_calendar_mapping_profile"
EVENT = "customer_calendar_event"
TENANT_MATCH = "tenant_id = nullif(current_setting('cip.customer_calendar_tenant_id', true), '')"


def _policies(table: str, commands: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for command in commands:
        name = f"cip_{table}_{command.lower()}"
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        if command == "INSERT":
            op.execute(f"CREATE POLICY {name} ON {table} FOR INSERT WITH CHECK ({TENANT_MATCH})")
        elif command == "UPDATE":
            op.execute(
                f"CREATE POLICY {name} ON {table} FOR UPDATE "
                f"USING ({TENANT_MATCH}) WITH CHECK ({TENANT_MATCH})"
            )
        else:
            op.execute(f"CREATE POLICY {name} ON {table} FOR {command} USING ({TENANT_MATCH})")
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


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PROFILE} (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            profile_code varchar(64) NOT NULL,
            display_name varchar(256) NOT NULL,
            header_row_index integer NOT NULL DEFAULT 1,
            sheet_name varchar(128),
            column_map_json jsonb NOT NULL,
            value_maps_json jsonb NOT NULL,
            is_default boolean NOT NULL DEFAULT false,
            notes text,
            updated_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{PROFILE} PRIMARY KEY (id),
            CONSTRAINT uq_customer_calendar_profile_tenant_code UNIQUE (tenant_id, profile_code),
            CONSTRAINT ck_{PROFILE}_header_row CHECK (header_row_index >= 1)
        )
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{PROFILE}_tenant_id ON {PROFILE} (tenant_id)")
    _policies(PROFILE, ("SELECT", "INSERT", "UPDATE", "DELETE"))

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EVENT} (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            customer_id integer NOT NULL REFERENCES dim_customer (id),
            name varchar(256) NOT NULL,
            kind varchar(16) NOT NULL DEFAULT 'other',
            start_date date NOT NULL,
            end_date date NOT NULL,
            upload_id varchar(128) NOT NULL,
            source_file varchar(512),
            source_row integer,
            file_sha256 varchar(64),
            profile_id integer REFERENCES {PROFILE} (id) ON DELETE SET NULL,
            raw_source_row jsonb,
            created_by varchar(256),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{EVENT} PRIMARY KEY (id),
            CONSTRAINT ck_customer_calendar_event_dates CHECK (end_date >= start_date),
            CONSTRAINT ck_customer_calendar_event_kind
                CHECK (kind IN ('campaign', 'pillar', 'other'))
        )
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{EVENT}_tenant_id ON {EVENT} (tenant_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{EVENT}_customer_id ON {EVENT} (customer_id)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{EVENT}_tenant_customer_dates "
        f"ON {EVENT} (tenant_id, customer_id, start_date, end_date)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{EVENT}_tenant_upload "
        f"ON {EVENT} (tenant_id, upload_id, customer_id)"
    )
    _policies(EVENT, ("SELECT", "INSERT", "DELETE"))


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {EVENT}")
    op.execute(f"DROP TABLE IF EXISTS {PROFILE}")

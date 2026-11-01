"""On the water: voyage columns on the three shipment tables, manual port conditions, shipment index drift.

Revision ID: 20261101_0049
Revises: 20261023_0048
Create Date: 2026-11-01

Approved by Warren (SPEC D3, .eif/audit/ON_THE_WATER_20261029/SPEC.md). Applying it to ``cip`` still needs his
"run against cip" after the clone proof.

1. ``shipment_evidence_line``, ``shipment_evidence_observation`` and ``fact_inbound_shipment`` get twelve
   nullable columns: ``on_board_date``, ``port_eta_date``, ``port_ata_date`` (date) and ``shipping_method``,
   ``forwarder_code``, ``origin_hub``, ``ship_way``, ``deliver_port``, ``vessel_name``, ``voyage_no``,
   ``bill_of_lading_no``, ``container_no`` (varchar). Nothing is backfilled here: the guarded script
   ``scripts/ops/backfill_shipment_water_fields.py`` fills them from ``raw_source_row``.
2. ``port_condition``: append-only manual port delays. SELECT and INSERT only (policies and grants); no
   UPDATE or DELETE policy, so under FORCE row security an update or delete matches no rows, for the owner
   too. The newest row per tenant and port is current. There is no tenant setting in the database (tenant
   scoping is the ``tenant_id`` column, applied by the API), so the policies are permissive.
3. Drift between ``cip`` and the models on the same three tables, fixed only where missing: the unique
   constraint ``uq_fact_inbound_shipment_fact_upsert_key`` and the indexes ``cip`` carries (created by
   20260630_0061 and later hand-made ones) that ``cip_test`` lacks; and the twin ``..._import_job_id``
   indexes the models used to declare on top of ``..._import_job`` (``cip_test`` only). On ``cip`` every
   part of step 3 is a no-op. ``fact_upsert_key`` NOT NULL is not touched (see schema_drift.txt).

Idempotent. Needs the table owner (on cip: ``postgres``): run with DATABASE_URL_SYNC_MIGRATE set to it.
The downgrade removes steps 1 and 2 only; step 3 puts ``cip_test`` where ``cip`` already was.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261101_0049"
down_revision: Union[str, Sequence[str], None] = "20261023_0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("shipment_evidence_line", "shipment_evidence_observation", "fact_inbound_shipment")
DATE_COLUMNS = ("on_board_date", "port_eta_date", "port_ata_date")
# Widths match app/models/shipment_water.py (a test pins the two together).
TEXT_COLUMNS: dict[str, int] = {
    "shipping_method": 256,
    "forwarder_code": 64,
    "origin_hub": 64,
    "ship_way": 64,
    "deliver_port": 32,
    "vessel_name": 128,
    "voyage_no": 64,
    "bill_of_lading_no": 64,
    "container_no": 64,
}

# The indexes cip carries on the three tables and the models now declare (name, table, definition).
INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_fact_inbound_shipment_customer_id", "fact_inbound_shipment", "(customer_id)"),
    ("ix_fact_inbound_shipment_distributor_id", "fact_inbound_shipment", "(distributor_id)"),
    ("ix_fact_inbound_shipment_product_id", "fact_inbound_shipment", "(product_id)"),
    ("ix_fact_inbound_shipment_shipment_evidence_line_id", "fact_inbound_shipment", "(shipment_evidence_line_id)"),
    ("ix_fact_inbound_shipment_source_key", "fact_inbound_shipment", "(source_key)"),
    ("ix_fact_inbound_shipment_woc_asof", "fact_inbound_shipment", "(distributor_id, product_id, pod_date, line_state)"),
    ("ix_shipment_evidence_line_customer_id", "shipment_evidence_line", "(customer_id)"),
    ("ix_shipment_evidence_line_distributor_id", "shipment_evidence_line", "(distributor_id)"),
    ("ix_shipment_evidence_line_product_id", "shipment_evidence_line", "(product_id)"),
    (
        "ix_shipment_evidence_line_active_corpus",
        "shipment_evidence_line",
        "(import_job_id) WHERE corpus_superseded_at IS NULL",
    ),
    (
        "ix_shipment_ev_obs_identity_latest",
        "shipment_evidence_observation",
        "(line_identity_key, valid_from DESC NULLS LAST, id DESC) INCLUDE (product_id, superseded_by_id)",
    ),
)
# (twin to drop, index that stays on the same column)
TWIN_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_shipment_evidence_line_import_job_id", "ix_shipment_evidence_line_import_job"),
    ("ix_shipment_evidence_observation_import_job_id", "ix_shipment_ev_obs_import_job"),
)
UNIQUE_NAME = "uq_fact_inbound_shipment_fact_upsert_key"


def _add_columns() -> None:
    for table in TABLES:
        for col in DATE_COLUMNS:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} date")
        for col, width in TEXT_COLUMNS.items():
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} varchar({width})")


def _port_condition() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS port_condition (
            id serial NOT NULL,
            tenant_id text NOT NULL DEFAULT 'default',
            port_code varchar(16) NOT NULL,
            delay_days numeric(8, 2) NOT NULL,
            note text,
            entered_by varchar(256) NOT NULL,
            entered_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_port_condition PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_port_condition_current ON port_condition (tenant_id, port_code, entered_at, id)"
    )
    op.execute("ALTER TABLE port_condition ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE port_condition FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS cip_port_condition_select ON port_condition")
    op.execute("DROP POLICY IF EXISTS cip_port_condition_insert ON port_condition")
    op.execute("CREATE POLICY cip_port_condition_select ON port_condition FOR SELECT USING (true)")
    op.execute("CREATE POLICY cip_port_condition_insert ON port_condition FOR INSERT WITH CHECK (true)")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT ON port_condition TO cip;
            GRANT USAGE, SELECT ON SEQUENCE port_condition_id_seq TO cip;
          END IF;
        END $$;
        """
    )


def _fix_drift() -> None:
    # The unique constraint, only where missing; refuse (as 20260630_0061 did) if it cannot hold.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = '{UNIQUE_NAME}' AND conrelid = 'fact_inbound_shipment'::regclass
          ) THEN
            IF EXISTS (
              SELECT 1 FROM fact_inbound_shipment WHERE fact_upsert_key IS NOT NULL
              GROUP BY fact_upsert_key HAVING count(*) > 1 LIMIT 1
            ) THEN
              RAISE EXCEPTION 'Duplicate fact_upsert_key rows: run scripts/merge_shipped_fact_identity_twins.py first';
            END IF;
            ALTER TABLE fact_inbound_shipment ADD CONSTRAINT {UNIQUE_NAME} UNIQUE (fact_upsert_key);
          END IF;
        END $$;
        """
    )
    for name, table, definition in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {definition}")
    for twin, kept in TWIN_INDEXES:
        # Drop the twin only while the index that stays is there, so the column is never left unindexed.
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = '{kept}') THEN
                DROP INDEX IF EXISTS {twin};
              END IF;
            END $$;
            """
        )


def upgrade() -> None:
    _add_columns()
    _port_condition()
    _fix_drift()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS port_condition")
    for table in TABLES:
        for col in (*DATE_COLUMNS, *TEXT_COLUMNS):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

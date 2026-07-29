"""Controlled system reference rows for Commercial Planner (global dimensions).

These are not demo data and must not be created from upload file tokens.

Provisioning (idempotent, safe to run multiple times):
- ``alembic upgrade head`` — migration calls the sync helper (offline + CI + prod).
- ``python scripts/seed.py --commercial-system-reference-only`` — repair path without wiping the DB.

Rows:
- ``dim_customer`` code ``OPEN_CHANNEL`` — controlled Open Channel account for lineup sync.
- ``dim_distributor`` code ``UNASSIGNED`` — placeholder when distributor is intentionally blank.

``DimCustomer`` / ``DimDistributor`` are global (no tenant/company column); uniqueness is on ``code``.
"""

from __future__ import annotations

from sqlalchemy import text

from app.services.commercial_planner.open_channel_customer import (
    OPEN_CHANNEL_CUSTOMER_CODE,
    OPEN_CHANNEL_CUSTOMER_NAME,
)
from app.services.commercial_planner.unassigned_distributor import (
    UNASSIGNED_DISTRIBUTOR_CODE,
    UNASSIGNED_DISTRIBUTOR_NAME,
)


def ensure_commercial_planner_system_reference_data_sync(conn) -> None:
    """Insert OPEN_CHANNEL + UNASSIGNED rows if missing. Synchronous for Alembic ``op.get_bind()``."""
    conn.execute(
        text(
            """
            INSERT INTO dim_distributor (code, name, distributor_status, created_at, updated_at)
            SELECT
                CAST(:code AS VARCHAR(32)),
                CAST(:name AS VARCHAR(256)),
                CAST('active' AS VARCHAR(32)),
                NOW(),
                NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM dim_distributor d WHERE d.code = CAST(:code AS VARCHAR(32))
            )
            """
        ),
        {"code": UNASSIGNED_DISTRIBUTOR_CODE, "name": UNASSIGNED_DISTRIBUTOR_NAME},
    )
    conn.execute(
        text(
            """
            INSERT INTO dim_customer (
                code, name, customer_status, is_key_account, partner_tier, account_owner_internal, notes_summary,
                region_id, channel_id, preferred_distributor_id, created_at, updated_at
            )
            SELECT
                CAST(:code AS VARCHAR(64)),
                CAST(:name AS VARCHAR(256)),
                CAST('active' AS VARCHAR(32)),
                CAST(FALSE AS BOOLEAN),
                CAST(NULL AS VARCHAR(32)),
                CAST(NULL AS VARCHAR(128)),
                CAST(NULL AS VARCHAR(512)),
                CAST(NULL AS INTEGER),
                CAST(NULL AS INTEGER),
                CAST(NULL AS INTEGER),
                NOW(),
                NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM dim_customer c WHERE c.code = CAST(:code AS VARCHAR(64))
            )
            """
        ),
        {"code": OPEN_CHANNEL_CUSTOMER_CODE, "name": OPEN_CHANNEL_CUSTOMER_NAME},
    )

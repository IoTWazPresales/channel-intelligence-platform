"""Pytest hooks shared by API tests.

Import-pipeline integration tests create `import_job` rows, staging lines, and storage keys
under `imports/test/...` using the same `DATABASE_URL` / `DATABASE_URL_SYNC` as local dev.
When that URL targets the default database name `cip`, those tests pollute the shared dev DB.

Guard posture (deny-by-default): when settings resolve to database name `cip` and
`ALLOW_TESTS_ON_DEV_DB` is unset, refuse ANY write-capable test module unless it appears
in `_CIP_WRITE_ALLOWLIST`. Fixture-local guards (e.g. `_assert_not_cip` in bulk smoke)
remain in force and are not weakened by this allowlist.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Historical hand-maintained frozenset (pre-deny-by-default). Kept as documentation of the
# original five import-pipeline modules; the live gate uses `_WRITE_CAPABLE_TEST_MODULES`.
_IMPORT_PIPELINE_DB_TEST_MODULES: frozenset[str] = frozenset(
    {
        "test_distributor_sales_inventory_import.py",
        "test_dsi_batch.py",
        "test_dsi_validate_bulk_staging.py",
        "test_historical_lineup_import.py",
        "test_historical_lineup_resolution.py",
    }
)

# Modules that open SessionLocal / AsyncSessionLocal / create_engine, or execute
# DELETE / TRUNCATE / INSERT / UPDATE / ORM .delete( against a real session.
# Enumerated 2026-08-02 via static scan of apps/api/tests/test_*.py.
_WRITE_CAPABLE_TEST_MODULES: frozenset[str] = frozenset(
    {
        "test_async_broker_dispatch.py",
        "test_backfill_shipment_customer_po.py",
        "test_background_tasks.py",
        "test_commercial_planner_api.py",
        "test_commercial_planner_reference_bootstrap.py",
        "test_cpor_cases_api.py",
        "test_cpor_historical_unit_c.py",
        "test_cst_mapping_candidates.py",
        "test_customer_alias_scope_merge.py",
        "test_customer_full_merge.py",
        "test_customers_delete.py",
        "test_data_integrity_audit.py",
        "test_distributor_full_merge.py",
        "test_distributor_sales_inventory_import.py",
        "test_dsi_apply_background.py",
        "test_dsi_batch.py",
        "test_dsi_bulk_map_customers_scope.py",
        "test_dsi_bulk_provisional_customers_reuse.py",
        "test_dsi_file_distributor.py",
        "test_dsi_resolution_cache_plain.py",
        "test_dsi_resolution_plan_apply_sync.py",
        "test_dsi_validate_bulk_staging.py",
        "test_dsi_validate_remote_supabase.py",
        "test_historical_lineup_import.py",
        "test_historical_lineup_resolution.py",
        "test_import_background_slots.py",
        "test_import_job_bulk_delete.py",
        "test_imports_templates.py",
        "test_lineup_bulk_backfill_apply_integration.py",
        "test_lineup_business_unit_resolution.py",
        "test_lineup_case_supersession_delete.py",
        "test_lineup_po_auto_link.py",
        "test_lineup_po_auto_link_actions.py",
        "test_master_bulk_delete_sql_integration.py",
        "test_pipeline_failure_writeback.py",
        "test_product_dsi_maintenance.py",
        "test_product_resolution_index_plain.py",
        "test_products_delete.py",
        "test_purchase_order.py",
        "test_running_import_job_reaper.py",
        "test_shipment_apply_hardening.py",
        "test_shipment_change_events.py",
        "test_shipment_evidence_observations.py",
        "test_shipment_evidence_orphan_purge.py",
        "test_shipment_invoice_graduation.py",
        "test_shipment_null_distributor_po_merge.py",
        "test_shipment_null_distributor_sibling_po_merge.py",
        "test_shipment_purchase_order_materialize.py",
        "test_shipment_resolved_entities.py",
        "test_shipment_steward_bulk_preview.py",
        "test_shipping_commercial_kpis.py",
        "test_sql_viewer.py",
        "test_task_run_ledger.py",
        "test_unified_lineup_import.py",
    }
)

# Modules allowed to run when settings resolve to `cip` without ALLOW_TESTS_ON_DEV_DB.
# Every entry must have an inline why-comment; keep this set minimal.
_CIP_WRITE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Requires live cip via `_require_cip` — supersession restore integration against real FKs.
        "test_lineup_case_supersession_delete.py",
    }
)

# Invariant: historical import-pipeline modules remain covered by the write-capable set.
assert _IMPORT_PIPELINE_DB_TEST_MODULES <= _WRITE_CAPABLE_TEST_MODULES


def _sqlalchemy_db_name(url: str) -> str:
    """Return the path segment after the last '/' in a SQLAlchemy-style URL (strip query string)."""
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return

    node_file = item.nodeid.split("::", 1)[0].replace("\\", "/")
    basename = Path(node_file).name
    if basename not in _WRITE_CAPABLE_TEST_MODULES:
        return
    if basename in _CIP_WRITE_ALLOWLIST:
        return

    from app.core.config import get_settings

    settings = get_settings()
    async_name = _sqlalchemy_db_name(settings.database_url)
    sync_name = _sqlalchemy_db_name(settings.database_url_sync)
    if async_name == "cip" or sync_name == "cip":
        pytest.fail(
            f"Refusing write-capable test module {basename!r}: database name is 'cip' "
            "(default shared dev DB). Point DATABASE_URL / DATABASE_URL_SYNC at a disposable "
            "database (e.g. .../cip_test), or set ALLOW_TESTS_ON_DEV_DB=1 to acknowledge writes "
            "to the current database, or add the module to _CIP_WRITE_ALLOWLIST with a "
            "justification comment if it genuinely requires cip."
        )

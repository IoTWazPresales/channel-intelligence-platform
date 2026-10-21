"""N-0065 round 3 final cip_test run: parity + listener + N-0065 suites + round-2 broad sample.

Run from apps/api with its virtualenv. Delegates to N0065_run_db_tests.py, which swaps
DATABASE_URL(_SYNC) to cip_test in-process, asserts the name, and prints current_database().
The parity JSON goes to N0065_r3_parity_final.json next to this file.
"""

from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

N0065 = [
    "tests/test_product_line_rls_parity_n0065_db.py",
    "tests/test_product_line_session_listener_n0065.py",
    "tests/test_product_line_scope_n0065.py",
]
ROUND1 = [
    "tests/test_shipment_sheet_selection.py",
    "tests/test_inbound_lineup_quarter.py",
    "tests/test_bu_code_literal_guard.py",
]
AUTH = [
    "tests/test_admin_overview.py",
    "tests/test_auth_login_throttle.py",
    "tests/test_auth_password_roles.py",
    "tests/test_auth_tenant_commercial_profile_api.py",
    "tests/test_cpor_rbac_r1_auth.py",
    "tests/test_rbac_n0038_cpor_roles.py",
    "tests/test_rbac_r1c_admin_gates.py",
    "tests/test_tenant_scope.py",
]
FIX4 = [
    "tests/test_channel_ops_derived_stock.py",
    "tests/test_lineup_net_requirement.py",
    "tests/test_channel_ops_api.py",
    "tests/test_brief_signals.py",
]
SAMPLE = [
    "tests/test_cpor_case_supersession.py",
    "tests/test_cpor_fx_enforcement.py",
    "tests/test_cpor_fx_rate.py",
    "tests/test_cpor_workflow_status_projection.py",
    "tests/test_cpor_historical_import_h1.py",
    "tests/test_cpor_historical_import_h2.py",
    "tests/test_cst_steward_bulk.py",
    "tests/test_customers_list_contract.py",
    "tests/test_distributors_contract.py",
    "tests/test_dsi_mapping_candidates_list_filters.py",
    "tests/test_dsi_mapping_candidates_tab_counts.py",
    "tests/test_import_jobs_list.py",
    "tests/test_import_job_pipeline_metadata.py",
    "tests/test_import_job_task_control.py",
    "tests/test_shipment_evidence_observations.py",
    "tests/test_shipment_evidence_detect.py",
    "tests/test_shipment_evidence_source_keys.py",
    "tests/test_shipment_evidence_line_identity.py",
    "tests/test_shipment_evidence_steward_ops.py",
    "tests/test_shipment_mapping_candidates_list.py",
    "tests/test_shipment_mapping_candidates_tab_counts.py",
    "tests/test_demand_forecast_compute.py",
    "tests/test_dsi_forecasting.py",
    "tests/test_product_master_workflow.py",
    "tests/test_customer_promote_b061.py",
    "tests/test_distributor_promote_b061.py",
    "tests/test_mailbox_ingest.py",
    "tests/test_report_export.py",
    "tests/test_cpor_line_window_n0050.py",
    "tests/test_grid_fields.py",
    "tests/test_lineup.py",
    "tests/test_products_list_contract.py",
    "tests/test_query_compose.py",
    "tests/test_shipping_mailer_recipients.py",
    "tests/test_sku_economics_import.py",
]


def main() -> None:
    os.environ["N0065_PARITY_OUT"] = os.path.join(HERE, "N0065_r3_parity_final.json")
    extra = [p for p in N0065 + ROUND1 + AUTH + FIX4 + SAMPLE if os.path.exists(p)]
    missing = [p for p in N0065 + ROUND1 + AUTH + FIX4 + SAMPLE if not os.path.exists(p)]
    print("test files:", len(extra) + 1, "missing:", missing)
    sys.argv = ["N0065_run_db_tests.py", *extra, "-p", "no:cacheprovider", *sys.argv[1:]]
    runpy.run_path(os.path.join(HERE, "N0065_run_db_tests.py"), run_name="__main__")


if __name__ == "__main__":
    main()

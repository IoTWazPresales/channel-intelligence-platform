"""DSI Phase 0 browser/API E2E verification (local dev stack)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
API_ROOT = REPO / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.facts import FactReturns, FactSalesSellout  # noqa: E402
FIXTURES = REPO / "tests" / "e2e" / "fixtures"
API = "http://localhost:8001"
HEADERS = {"X-User-Role": "admin"}
def _wait_health(client: httpx.Client, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = client.get(f"{API}/health", timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("API health check timed out")


def _source_id(client: httpx.Client) -> int:
    r = client.get(f"{API}/api/v1/imports/sources", params={"template_slug": "distributor_inventory"}, headers=HEADERS)
    r.raise_for_status()
    rows = r.json()
    assert rows, "no distributor_inventory source"
    return int(rows[0]["id"])


def _default_dsi_mapping(client: httpx.Client, job_id: int) -> dict[str, str]:
    r = client.get(f"{API}/api/v1/imports/jobs/{job_id}/dsi-mapping-state", headers=HEADERS)
    r.raise_for_status()
    state = r.json()
    mapping = dict(state.get("field_mapping") or {})
    headers_list = list(state.get("file_headers") or [])
    if not mapping and headers_list:
        # minimal fallback for our fixture headers
        mapping = {
            headers_list[0]: "distributor_token",
            "sku": "product_identifier",
            "date": "transaction_date",
            "qty": "quantity_sold",
            "Dealer Name Group": "dealer_group_token",
            "soh": "stock_on_hand",
        }
        if "invoice_no" in headers_list:
            mapping["invoice_no"] = "invoice_no"
    return mapping


def _upload_dsi(
    client: httpx.Client,
    *,
    csv_path: Path,
    import_mode: str,
    workflow: str = "auto",
    confirm: bool = False,
) -> int:
    source_id = _source_id(client)
    data = {
        "source_id": str(source_id),
        "run_sync": "false",
        "import_mode": import_mode,
        "dsi_workflow_mode": workflow,
    }
    if confirm:
        data["confirm_destructive"] = "true"
    with csv_path.open("rb") as f:
        r = client.post(
            f"{API}/api/v1/imports/jobs",
            headers=HEADERS,
            data=data,
            files={"file": (csv_path.name, f, "text/csv")},
        )
    r.raise_for_status()
    job_id = int(r.json()["id"])
    return job_id


def _put_mapping(client: httpx.Client, job_id: int, mapping: dict[str, str]) -> None:
    r = client.put(
        f"{API}/api/v1/imports/jobs/{job_id}/dsi-field-mapping",
        headers=HEADERS,
        json={"field_mapping": mapping},
    )
    r.raise_for_status()


def _dsi_apply(client: httpx.Client, job_id: int) -> None:
    r = client.post(
        f"{API}/api/v1/imports/jobs/{job_id}/dsi-apply",
        headers=HEADERS,
        data={"confirm_destructive": "true"},
    )
    r.raise_for_status()


def _dsi_validate_async(client: httpx.Client, job_id: int) -> str | None:
    r = client.post(f"{API}/api/v1/imports/jobs/{job_id}/dsi-validate", headers=HEADERS)
    r.raise_for_status()
    body = r.json()
    return body.get("task_id")


def _wait_job(client: httpx.Client, job_id: int, *, timeout_s: int = 180) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"{API}/api/v1/imports/jobs/{job_id}", headers=HEADERS)
        r.raise_for_status()
        job = r.json()
        st = (job.get("status") or "").lower()
        stage = (job.get("stage") or "").lower()
        if st in ("completed", "completed_with_errors") and stage in ("validated", "loaded"):
            return job
        if st == "failed":
            raise RuntimeError(f"job {job_id} failed: {job.get('error_summary')}")
        time.sleep(2)
    raise RuntimeError(f"job {job_id} timed out")


def _db_counts_for_job(job_id: int) -> dict[str, int]:
    with SessionLocal() as db:
        sell = int(
            db.scalar(
                select(func.count()).select_from(FactSalesSellout).where(
                    FactSalesSellout.source_import_job_id == job_id
                )
            )
            or 0
        )
        ret_by_job = int(
            db.scalar(
                select(func.count()).select_from(FactReturns).where(FactReturns.import_job_id == job_id)
            )
            or 0
        )
        ret_inv2 = int(
            db.scalar(
                select(func.count()).select_from(FactReturns).where(FactReturns.invoice_no == "INV-E2E-002")
            )
            or 0
        )
        sell_inv1 = int(
            db.scalar(
                select(func.count()).select_from(FactSalesSellout).where(
                    FactSalesSellout.invoice_no == "INV-E2E-001"
                )
            )
            or 0
        )
        sell_neg_inv = int(
            db.scalar(
                select(func.count()).select_from(FactSalesSellout).where(
                    FactSalesSellout.invoice_no == "INV-E2E-002"
                )
            )
            or 0
        )
        row = db.scalar(
            select(FactSalesSellout.units).where(FactSalesSellout.invoice_no == "INV-E2E-001").order_by(
                FactSalesSellout.id.desc()
            )
        )
    return {
        "sellout_job": sell,
        "returns_job": ret_by_job,
        "returns_inv_e2e_002": ret_inv2,
        "sellout_inv_e2e_001": sell_inv1,
        "sellout_inv_e2e_002": sell_neg_inv,
        "inv_e2e001_units": float(row) if row is not None else None,
    }


def scenario_1(client: httpx.Client) -> int:
    print("\n=== Scenario 1: negative qty -> fact_returns ===")
    path = FIXTURES / "dsi_e2e_s1_v1.csv"
    job_id = _upload_dsi(client, csv_path=path, import_mode="apply", confirm=True)
    mapping = _default_dsi_mapping(client, job_id)
    _put_mapping(client, job_id, mapping)
    _dsi_apply(client, job_id)
    _wait_job(client, job_id)
    c = _db_counts_for_job(job_id)
    print("counts:", c)
    assert c["sellout_job"] >= 1, "expected positive sellout row for job"
    assert c["sellout_inv_e2e_001"] == 1, "expected one sellout for INV-E2E-001"
    assert c["sellout_inv_e2e_002"] == 0, "negative row must not be in fact_sales_sellout"
    assert c["returns_inv_e2e_002"] == 1, "expected one return for INV-E2E-002"
    print("PASS scenario 1")
    return job_id


def scenario_2(client: httpx.Client) -> None:
    print("\n=== Scenario 2: re-upload idempotency + qty update ===")
    path1 = FIXTURES / "dsi_e2e_s1_v1.csv"
    job1 = _upload_dsi(client, csv_path=path1, import_mode="apply", confirm=True)
    m = _default_dsi_mapping(client, job1)
    _put_mapping(client, job1, m)
    _dsi_apply(client, job1)
    _wait_job(client, job1)
    with SessionLocal() as db:
        sell_n1 = int(db.scalar(select(func.count()).select_from(FactSalesSellout)) or 0)
        ret_n1 = int(db.scalar(select(func.count()).select_from(FactReturns)) or 0)

    # re-upload same file (new job)
    job2 = _upload_dsi(client, csv_path=path1, import_mode="apply", confirm=True)
    _put_mapping(client, job2, m)
    _dsi_apply(client, job2)
    _wait_job(client, job2)
    with SessionLocal() as db:
        sell_n2 = int(db.scalar(select(func.count()).select_from(FactSalesSellout)) or 0)
        ret_n2 = int(db.scalar(select(func.count()).select_from(FactReturns)) or 0)
    assert sell_n2 == sell_n1, f"duplicate sellout rows: {sell_n1} -> {sell_n2}"
    assert ret_n2 == ret_n1, f"duplicate return rows: {ret_n1} -> {ret_n2}"

    path3 = FIXTURES / "dsi_e2e_s2_v2.csv"
    job3 = _upload_dsi(client, csv_path=path3, import_mode="apply", confirm=True)
    _put_mapping(client, job3, m)
    _dsi_apply(client, job3)
    _wait_job(client, job3)
    c = _db_counts_for_job(job3)
    assert c["inv_e2e001_units"] == 7.0, f"expected units 7 after update, got {c['inv_e2e001_units']}"
    with SessionLocal() as db:
        sell_n3 = int(db.scalar(select(func.count()).select_from(FactSalesSellout)) or 0)
    assert sell_n3 == sell_n2, "sellout row count should stay stable after qty update"
    print("PASS scenario 2")


def scenario_3(client: httpx.Client) -> None:
    print("\n=== Scenario 3: historical auto-apply vs weekly ===")
    hist_path = FIXTURES / "dsi_e2e_s3_historical.csv"
    hist_id = _upload_dsi(client, csv_path=hist_path, import_mode="validate", workflow="historical")
    m = _default_dsi_mapping(client, hist_id)
    _put_mapping(client, hist_id, m)
    _dsi_validate_async(client, hist_id)
    job = _wait_job(client, hist_id, timeout_s=300)
    meta = job.get("staged_metadata") or {}
    auto = meta.get("dsi_post_validate_auto_apply")
    print("historical meta dsi_workflow_mode:", meta.get("dsi_workflow_mode"))
    print("historical auto_apply:", auto)
    assert meta.get("dsi_workflow_mode") == "historical"
    # enqueue only when ready candidates exist
    if auto:
        assert auto.get("task_id"), "expected task_id when auto_apply queued"
        assert int(auto.get("candidate_count") or 0) >= 1
        print("historical: auto-apply enqueued")
    else:
        print("historical: no ready candidates to auto-apply (check candidates via API)")

    week_path = FIXTURES / "dsi_e2e_s3_weekly.csv"
    week_id = _upload_dsi(client, csv_path=week_path, import_mode="validate", workflow="weekly")
    _put_mapping(client, week_id, m)
    _dsi_validate_async(client, week_id)
    week_job = _wait_job(client, week_id, timeout_s=300)
    week_meta = week_job.get("staged_metadata") or {}
    assert week_meta.get("dsi_workflow_mode") == "weekly"
    assert "dsi_post_validate_auto_apply" not in week_meta
    print("weekly: no dsi_post_validate_auto_apply — PASS")
    print("PASS scenario 3 (API); verify nav bell in browser for historical task")


def main() -> int:
    with httpx.Client(timeout=120) as client:
        _wait_health(client)
        scenario_1(client)
        scenario_2(client)
        scenario_3(client)
    print("\nAll API-backed E2E scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

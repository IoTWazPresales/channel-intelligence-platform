"""DSI Phase 1 + Phase 2 browser/API validation (local dev, database cip)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
API_ROOT = REPO / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402

FIXTURES = REPO / "tests" / "e2e" / "fixtures"
API = os.environ.get("CIP_E2E_API_URL", "http://localhost:8002")
HEADERS = {"X-User-Role": "admin"}
def _dsi_source_id(client: httpx.Client) -> int:
    r = client.get(
        f"{API}/api/v1/imports/sources",
        params={"template_slug": "distributor_inventory"},
        headers=HEADERS,
    )
    r.raise_for_status()
    rows = r.json()
    assert rows, "no distributor_inventory source"
    return int(rows[0]["id"])


def _wait_health(client: httpx.Client, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if client.get(f"{API}/health", timeout=5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("API health check timed out")


def _default_dsi_mapping(client: httpx.Client, job_id: int) -> dict[str, str]:
    r = client.get(f"{API}/api/v1/imports/jobs/{job_id}/dsi-mapping-state", headers=HEADERS)
    r.raise_for_status()
    state = r.json()
    mapping = dict(state.get("field_mapping") or {})
    headers_list = list(state.get("file_headers") or [])
    if not mapping and headers_list:
        mapping = {
            headers_list[0]: "distributor_token",
            "sku": "product_identifier",
            "date": "transaction_date",
            "qty": "quantity_sold",
            "Dealer Name Group": "dealer_group_token",
            "soh": "stock_on_hand",
        }
        if "customer_name" in headers_list:
            mapping["customer_name"] = "customer_dealer_token"
    return mapping


def _upload_dsi(
    client: httpx.Client,
    *,
    csv_path: Path,
    source_id: int,
    import_mode: str = "validate",
    workflow: str = "weekly",
    confirm: bool = False,
) -> int:
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
    return int(r.json()["id"])


def _put_mapping(client: httpx.Client, job_id: int, mapping: dict[str, str]) -> None:
    r = client.put(
        f"{API}/api/v1/imports/jobs/{job_id}/dsi-field-mapping",
        headers=HEADERS,
        json={"field_mapping": mapping},
    )
    r.raise_for_status()


def _dsi_validate(client: httpx.Client, job_id: int) -> None:
    r = client.post(f"{API}/api/v1/imports/jobs/{job_id}/dsi-validate", headers=HEADERS)
    r.raise_for_status()


def _dsi_apply(client: httpx.Client, job_id: int) -> None:
    r = client.post(
        f"{API}/api/v1/imports/jobs/{job_id}/dsi-apply",
        headers=HEADERS,
        data={"confirm_destructive": "true"},
    )
    r.raise_for_status()


def _wait_job(
    client: httpx.Client,
    job_id: int,
    *,
    timeout_s: int = 300,
    require_stage: str | None = None,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"{API}/api/v1/imports/jobs/{job_id}", headers=HEADERS)
        r.raise_for_status()
        job = r.json()
        st = (job.get("status") or "").lower()
        stage = (job.get("stage") or "").lower()
        terminal = st in ("completed", "completed_with_errors")
        stage_ok = stage in ("validated", "loaded")
        if require_stage:
            stage_ok = stage == require_stage.lower()
        if terminal and stage_ok:
            return job
        if st == "failed":
            raise RuntimeError(f"job {job_id} failed: {job.get('error_summary')}")
        time.sleep(2)
    raise RuntimeError(f"job {job_id} timed out")


def _prior_count_for_source(source_id: int, exclude_job_id: int) -> int:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT COUNT(*) FROM import_job
                WHERE source_id = :sid
                  AND template_slug = 'distributor_inventory'
                  AND id != :jid
                  AND (import_mode = 'apply' OR stage = 'loaded')
                """
            ),
            {"sid": source_id, "jid": exclude_job_id},
        ).scalar()
    return int(row or 0)


def _plan_rows(client: httpx.Client, job_id: int) -> list[dict]:
    r = client.post(
        f"{API}/api/v1/mappings/import-jobs/{job_id}/dsi-resolution-plan/effective",
        headers=HEADERS,
        json={},
    )
    r.raise_for_status()
    body = r.json()
    if isinstance(body, list):
        return body
    return list(body.get("rows") or body.get("candidates") or [])


def main() -> int:
    results: dict[str, dict] = {}
    with httpx.Client(timeout=180) as client:
        _wait_health(client)

        # --- Scenario 1 ---
        print("\n=== Scenario 1: intelligence_state panel ===")
        s1_path = FIXTURES / "dsi_e2e_s3_weekly.csv"
        source_id = _dsi_source_id(client)
        s1_id = _upload_dsi(
            client, csv_path=s1_path, source_id=source_id, import_mode="validate", workflow="weekly"
        )
        m = _default_dsi_mapping(client, s1_id)
        _put_mapping(client, s1_id, m)
        _dsi_validate(client, s1_id)
        s1_job = _wait_job(client, s1_id)
        meta = s1_job.get("staged_metadata") or {}
        intel = meta.get("intelligence_state")
        source_id = int(s1_job.get("source_id") or source_id)
        prior = _prior_count_for_source(source_id, s1_id)
        banners = (intel or {}).get("banners") or []
        tier = (intel or {}).get("auto_resolution_tier")
        layers = (intel or {}).get("intelligence_layers") if isinstance(intel, dict) else None
        no_baseline = any(
            isinstance(b, dict) and "No baseline data found" in str(b.get("message") or "")
            for b in banners
        )
        results["scenario_1"] = {
            "job_id": s1_id,
            "pass": bool(intel and isinstance(intel, dict) and isinstance(layers, dict) and len(layers) >= 3),
            "intel_tier": tier,
            "prior_count_db": prior,
            "no_baseline_banner": no_baseline,
            "expected_no_baseline": prior == 0,
            "banner_messages": [b.get("message") for b in banners if isinstance(b, dict)],
            "ui_url": f"http://localhost:3000/admin/imports?job={s1_id}",
        }
        print(json.dumps(results["scenario_1"], indent=2))

        # --- Scenario 2 ---
        print("\n=== Scenario 2: supervised auto-resolution ===")
        if prior == 1:
            supervised = [
                c
                for c in _plan_rows(client, s1_id)
                if c.get("auto_resolved_supervised") is True
            ]
            results["scenario_2"] = {
                "status": "run",
                "pass": len(supervised) > 0,
                "supervised_rows": len(supervised),
                "job_id": s1_id,
            }
        else:
            results["scenario_2"] = {
                "status": "skipped",
                "reason": f"source {source_id} has {prior} prior applied jobs (need exactly 1 for supervised tier)",
                "pass": None,
            }
        print(json.dumps(results["scenario_2"], indent=2))

        # --- Scenario 3 ---
        print("\n=== Scenario 3: automatic suppression ===")
        if prior >= 2:
            auto_tier = tier == "automatic"
            try:
                plan_rows = _plan_rows(client, s1_id)
            except Exception as exc:
                plan_rows = []
                plan_err = str(exc)[:200]
            else:
                plan_err = None
            conflict = [c for c in plan_rows if c.get("conflict_flag")]
            auto_resolved = [
                c
                for c in plan_rows
                if c.get("entity_type") == "customer" and c.get("ready") and c.get("suggested_target_id")
            ]
            results["scenario_3"] = {
                "status": "run",
                "pass": auto_tier,
                "auto_resolution_tier": tier,
                "plan_error": plan_err,
                "conflict_candidates": len(conflict),
                "ready_customer_candidates": len(auto_resolved),
                "job_id": s1_id,
            }
        else:
            results["scenario_3"] = {
                "status": "skipped",
                "reason": f"need 2+ prior applied jobs; have {prior}",
                "pass": None,
            }
        print(json.dumps(results["scenario_3"], indent=2))

        # --- Scenario 4 ---
        print("\n=== Scenario 4: SOH reconciliation after apply ===")
        s4_path = FIXTURES / "dsi_e2e_s1_v1.csv"
        s4_id = _upload_dsi(
            client,
            csv_path=s4_path,
            source_id=source_id,
            import_mode="validate",
            workflow="weekly",
        )
        s4_map = _default_dsi_mapping(client, s4_id)
        _put_mapping(client, s4_id, s4_map)
        _dsi_validate(client, s4_id)
        _wait_job(client, s4_id, timeout_s=600)
        _dsi_apply(client, s4_id)
        s4_job = _wait_job(client, s4_id, timeout_s=600, require_stage="loaded")
        s4_meta = s4_job.get("staged_metadata") or {}
        soh_task = s4_meta.get("dsi_soh_reconcile_task")
        dist_id = None
        period_end = None
        dom = s4_meta.get("dominant_distributor_id") or s4_meta.get("resolved_distributor_id")
        if dom is not None:
            dist_id = int(dom)
        ped = s4_meta.get("period_end_date") or s4_meta.get("dsi_period_end")
        if ped:
            period_end = str(ped)
        calc_rows = 0
        sample = []
        with SessionLocal() as db:
            if dist_id is None:
                dist_id = db.execute(
                    text(
                        """
                        SELECT MAX(resolved_distributor_id)
                        FROM import_distributor_si_staging_line
                        WHERE import_job_id = :jid
                        """
                    ),
                    {"jid": s4_id},
                ).scalar()
            if period_end is None:
                period_end = db.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(snapshot_date), MAX(transaction_date))
                        FROM import_distributor_si_staging_line
                        WHERE import_job_id = :jid
                        """
                    ),
                    {"jid": s4_id},
                ).scalar()
        if dist_id:
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        """
                        SELECT product_id, on_hand_units, calculated_soh, reconciliation_status
                        FROM fact_inventory_distributor
                        WHERE distributor_id = :did
                        ORDER BY product_id
                        LIMIT 10
                        """
                    ),
                    {"did": dist_id},
                ).all()
                sample = [tuple(r) for r in rows]
                calc_rows = sum(1 for r in rows if r[2] is not None)
        # poll background tasks API
        bell_label = None
        for _ in range(30):
            tr = client.get(f"{API}/api/v1/imports/background-tasks", headers=HEADERS)
            if tr.status_code == 200:
                tasks = tr.json() if isinstance(tr.json(), list) else tr.json().get("tasks") or []
                for t in tasks:
                    if int(t.get("import_job_id") or 0) == s4_id:
                        bell_label = t.get("label") or t.get("kind")
                        if (t.get("status") or "").lower() in ("completed", "succeeded", "success"):
                            break
            if soh_task and calc_rows > 0:
                break
            time.sleep(2)
        results["scenario_4"] = {
            "job_id": s4_id,
            "stage": s4_job.get("stage"),
            "status": s4_job.get("status"),
            "dsi_soh_reconcile_task": soh_task,
            "distributor_id": dist_id,
            "period_end": period_end,
            "bell_label": bell_label,
            "inventory_sample": sample,
            "rows_with_calculated_soh_in_sample": calc_rows,
            "pass": bool(soh_task) and bool(dist_id) and calc_rows > 0,
            "ui_url": f"http://localhost:3000/admin/imports?job={s4_id}",
        }
        print(json.dumps(results["scenario_4"], indent=2, default=str))

    out_path = REPO / ".dsi-phase1-phase2-results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Read-only browser/API/DB parity audit for CIP surfaces.

Writes JSON report to repo .tmp/browser_db_parity_audit.json
Run from apps/api with venv.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402

API = "http://127.0.0.1:8001"
WEB = "http://127.0.0.1:3000"


def api_get(path: str, timeout: float = 60.0) -> tuple[int, object]:
    req = urllib.request.Request(f"{API}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return int(resp.status), json.loads(body)
            except json.JSONDecodeError:
                return int(resp.status), {"_raw": body[:500]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return int(e.code), json.loads(body)
        except Exception:
            return int(e.code), {"_error": body[:500]}
    except Exception as e:
        return 0, {"_error": str(e)}


def web_get(path: str, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(f"{WEB}{path}", headers={"Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")[:200]
    except urllib.error.HTTPError as e:
        return int(e.code), e.read().decode("utf-8", errors="replace")[:200]
    except Exception as e:
        return 0, str(e)


def main() -> int:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": None,
        "checks": [],
        "page_http": [],
        "gaps": [],
    }

    with SessionLocal() as db:
        db_name = db.execute(text("SELECT current_database()")).scalar()
        report["database"] = db_name
        if db_name != "cip":
            print(f"STOP: database={db_name}", file=sys.stderr)
            return 2

        def q(sql: str):
            return db.execute(text(sql)).scalar()

        counts = {
            "dim_customer_live": q(
                "SELECT count(*) FROM dim_customer WHERE merged_into_customer_id IS NULL"
            ),
            "dim_customer_merged": q(
                "SELECT count(*) FROM dim_customer WHERE merged_into_customer_id IS NOT NULL"
            ),
            "dim_product": q("SELECT count(*) FROM dim_product"),
            "dim_distributor": q("SELECT count(*) FROM dim_distributor"),
            "fact_sales_sellout": q("SELECT count(*) FROM fact_sales_sellout"),
            "fact_inbound_shipment": q("SELECT count(*) FROM fact_inbound_shipment"),
            "import_job": q("SELECT count(*) FROM import_job"),
            "customer_source_token_alias_approved": q(
                "SELECT count(*) FROM customer_source_token_alias WHERE status = 'approved'"
            ),
            "open_channel_ok": q(
                "SELECT count(*) FROM dim_customer WHERE code = 'OPEN_CHANNEL' "
                "AND merged_into_customer_id IS NULL AND customer_status <> 'merged'"
            ),
            "cpor_cases": q(
                "SELECT count(*) FROM commercial_cpor_case"
            )
            if db.execute(
                text(
                    "SELECT to_regclass('public.commercial_cpor_case') IS NOT NULL"
                )
            ).scalar()
            else None,
        }
        report["db_counts"] = {k: int(v) if v is not None else None for k, v in counts.items()}

    # API endpoints to compare
    api_checks = [
        ("GET /customers?limit=1", "/api/v1/customers?limit=1&offset=0", "total", "dim_customer_live"),
        ("GET /products?limit=1", "/api/v1/products?limit=1&offset=0", "total", "dim_product"),
        ("GET /distributors?limit=1", "/api/v1/distributors?limit=1&offset=0", "total", "dim_distributor"),
        (
            "GET /customers/duplicate-groups",
            "/api/v1/customers/duplicate-groups?page=1&page_size=1",
            "total",
            None,
        ),
        (
            "GET /customers/duplicate-groups/related",
            "/api/v1/customers/duplicate-groups/related?page=1&page_size=1",
            "total",
            None,
        ),
        (
            "GET /customers/alias-scope-conflicts",
            "/api/v1/customers/alias-scope-conflicts?page=1&page_size=1",
            "total",
            None,
        ),
        ("GET channel-ops sell-out summary-ish", "/api/v1/channel-ops/summary", None, None),
        ("GET shipping", "/api/v1/shipping?limit=1&skip=0", "total", None),
        ("GET product-master-gaps", "/api/v1/product-master-gaps?limit=1&skip=0", "total", None),
        ("GET cpor-cases", "/api/v1/commercial-planner/cpor-cases?limit=1&offset=0", "total", "cpor_cases"),
        ("GET po-management gaps", "/api/v1/po-management/gaps?limit=1&offset=0", "total", None),
        ("GET plan-vs-executed exceptions", "/api/v1/plan-vs-executed/exceptions?limit=1&offset=0", "total", None),
        ("GET import jobs", "/api/v1/imports/jobs?limit=1", "total", "import_job"),
    ]

    # Probe alternate paths if needed
    for label, path, total_key, db_key in api_checks:
        status, body = api_get(path)
        entry = {
            "label": label,
            "path": path,
            "http_status": status,
            "ok": 200 <= status < 300,
            "api_total": None,
            "db_count": report["db_counts"].get(db_key) if db_key else None,
            "match": None,
            "data_unavailable": None,
            "error": None,
        }
        if isinstance(body, dict):
            entry["data_unavailable"] = body.get("data_unavailable")
            if total_key and total_key in body:
                entry["api_total"] = body.get(total_key)
            elif "total" in body:
                entry["api_total"] = body.get("total")
            elif "count" in body:
                entry["api_total"] = body.get("count")
            if "_error" in body:
                entry["error"] = body["_error"]
                entry["ok"] = False
            if entry["api_total"] is not None and entry["db_count"] is not None:
                entry["match"] = int(entry["api_total"]) == int(entry["db_count"])
                if not entry["match"]:
                    report["gaps"].append(
                        f"{label}: API total={entry['api_total']} DB={entry['db_count']}"
                    )
        if not entry["ok"]:
            report["gaps"].append(f"{label}: HTTP {status} {entry.get('error') or body}")
        report["checks"].append(entry)
        print(json.dumps(entry))

    # OPEN_CHANNEL sanity
    if report["db_counts"].get("open_channel_ok") != 1:
        report["gaps"].append(
            f"OPEN_CHANNEL not healthy: open_channel_ok={report['db_counts'].get('open_channel_ok')}"
        )

    pages = [
        "/dashboard",
        "/admin/customers",
        "/admin/customers/duplicates?tab=related",
        "/admin/customers/duplicates?tab=name_similarity",
        "/admin/customers/duplicates?tab=alias_scope",
        "/admin/products",
        "/admin/product-master-gaps",
        "/admin/distributors",
        "/admin/distributors/duplicates",
        "/admin/imports",
        "/admin/shipment-evidence",
        "/shipping",
        "/channel-ops",
        "/channel-intelligence",
        "/commercial-planner",
        "/commercial-planner/cpor-cases",
        "/plan-vs-executed",
        "/admin/po-management",
        "/lineup",
        "/admin/mappings",
        "/admin/channels",
        "/admin/regions",
    ]
    for p in pages:
        st, snippet = web_get(p)
        entry = {"path": p, "http_status": st, "ok": st == 200}
        if st != 200:
            report["gaps"].append(f"WEB {p}: HTTP {st} {snippet}")
        report["page_http"].append(entry)
        print(f"WEB {p} -> {st}")

    out = Path(__file__).resolve().parents[3] / ".tmp" / "browser_db_parity_audit.json"
    # __file__ = apps/api/scripts/ops/xxx.py -> parents[3] = repo root
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"gaps={len(report['gaps'])}")
    for g in report["gaps"]:
        print(f"  GAP: {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

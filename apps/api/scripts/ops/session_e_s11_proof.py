"""SESSION E S11 — prove worker/API DB binding and re-run shipment apply on cip_test.

Prints DATABASE_* dbnames from .env (worker default) vs GET /health/ready (API).
Re-runs apply with worker env rewritten to cip_test when mismatch is suspected.
Every SQL block prints current_database().
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(OPS_DIR))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from app.models.dimensions import DimProduct  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402
from session_e_cip_test_walk import (  # noqa: E402
    STAMP,
    build_shipment_csv_bytes,
    create_validated_shipment_job,
    http_json,
    login_admin,
    poll_progress,
    q,
    require_cip_test_api,
    rewrite_dbname,
    seed_shipment_product,
)

ENV_FILE = API_ROOT / ".env"
DB_KEYS = ("DATABASE_URL", "DATABASE_URL_SYNC", "DATABASE_URL_SYNC_MIGRATE")


def _parse_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _url_dbname(url: str) -> str:
    path = urlparse(url).path or ""
    return path.lstrip("/") or "(empty)"


def print_binding_evidence() -> None:
    file_vals = _parse_env_file()
    print("=== DB binding evidence ===")
    print(".env file (default Celery worker reads on startup):")
    for k in DB_KEYS:
        val = file_vals.get(k) or os.environ.get(k) or ""
        print(f"  {k} dbname={_url_dbname(val) if val else '(unset)'}")
    code, body = http_json("GET", "http://127.0.0.1:8001/health/ready", timeout=10.0)
    print("GET /health/ready status", code)
    print("GET /health/ready body", body)
    if code == 200:
        api_db = json.loads(body).get("database")
        worker_db = _url_dbname(file_vals.get("DATABASE_URL_SYNC") or file_vals.get("DATABASE_URL") or "")
        print("BINDING_COMPARISON api_database=", api_db, "worker_default_dbname=", worker_db)
        if api_db and worker_db and api_db != worker_db:
            print(
                "BINDING_MISMATCH: API on",
                api_db,
                "but worker .env default is",
                worker_db,
                "— Celery tasks may stall or write to the wrong DB.",
            )
        else:
            print("BINDING_MATCH_OR_INCONCLUSIVE")
    print()


def main() -> int:
    print("=== SESSION E S11 proof rerun ===\n")
    print_binding_evidence()
    require_cip_test_api()

    sync = get_settings().database_url_sync
    target = sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test"))
    engine = create_engine(target)

    ship_job_id: int
    with Session(engine) as session:
        q(session, "SELECT current_database()", "pre-seed")
        seed_shipment_product(session)
        ship_job_id = create_validated_shipment_job(session)

    token = login_admin()
    print("--- POST shipment apply (S11 rerun) job", ship_job_id, "---")
    code, body = http_json(
        "POST",
        f"http://127.0.0.1:8001/api/v1/shipment-evidence/jobs/{ship_job_id}/apply",
        {},
        token=token,
    )
    print("status", code)
    print(body[:4000])
    apply_payload = json.loads(body) if code in (200, 202) else {}
    print()

    transitions: list[dict] = []

    def poll_with_log(job_id: int, max_wait: float = 120.0) -> dict | None:
        deadline = time.time() + max_wait
        last: dict | None = None
        while time.time() < deadline:
            c, b = http_json(
                "GET",
                f"http://127.0.0.1:8001/api/v1/imports/jobs/{job_id}/dsi-progress",
                token=token,
            )
            if c == 200:
                last = json.loads(b)
                snap = {
                    "t": round(time.time(), 1),
                    "phase": last.get("phase"),
                    "task_state": last.get("task_state"),
                    "pct": last.get("pct"),
                    "status": last.get("status"),
                }
                transitions.append(snap)
                print("S11 poll", json.dumps(snap))
                phase = (last or {}).get("phase") or (last or {}).get("status")
                pct = (last or {}).get("pct")
                if phase in ("done", "complete", "failed", "error", "loaded") or pct == 100:
                    return last
                if (last or {}).get("complete") is True:
                    return last
            time.sleep(2)
        return last

    final_progress: dict | None = None
    if apply_payload.get("async"):
        final_progress = poll_with_log(int(ship_job_id))

    with Session(engine) as session:
        q(
            session,
            "SELECT id, stage, status, import_mode FROM import_job WHERE id = :id",
            "Shipment job terminal state",
            {"id": ship_job_id},
        )
        fact_rows = q(
            session,
            "SELECT count(*) FROM fact_inbound_shipment WHERE source_key LIKE :pfx",
            "fact_inbound_shipment count",
            {"pfx": f"%{STAMP}%"},
        )

    print("PHASE_TRANSITIONS", json.dumps(transitions, indent=2))
    print(
        "FINAL_PROGRESS",
        json.dumps(
            {
                "task_state": (final_progress or {}).get("task_state"),
                "phase": (final_progress or {}).get("phase"),
                "pct": (final_progress or {}).get("pct"),
                "status": (final_progress or {}).get("status"),
            },
            indent=2,
        ),
    )
    print("SHIPMENT_JOB_ID", ship_job_id)
    print("FACT_ROW_COUNT", fact_rows[0][0] if fact_rows else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

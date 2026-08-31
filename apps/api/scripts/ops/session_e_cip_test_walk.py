"""SESSION E unit 11 — HL seed + shipment apply/progress on cip_test.

STOP if GET /health/ready is not database=cip_test. No writes in that case.
Every SQL block prints current_database(). HTTP writes require admin login.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

import pandas as pd

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from app.ingestion.pipeline import process_import_job_sync  # noqa: E402
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition  # noqa: E402
from app.services.seed_demo import _seed_import_core  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

API = "http://127.0.0.1:8001"
FIXTURE_DIR = Path(__file__).resolve().parent
HL_FIXTURE = FIXTURE_DIR / "session_e_hl_fixture.xlsx"
SHIP_FIXTURE = FIXTURE_DIR / "session_e_shipment_fixture.csv"
STAMP = "SESSION-E-20260831"


def rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def http_json(
    method: str,
    url: str,
    payload: dict | None = None,
    token: str | None = None,
    timeout: float = 120.0,
) -> tuple[int | None, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except URLError as e:
        return None, f"{type(e).__name__}: {e}"


def require_cip_test_api() -> dict:
    code, body = http_json("GET", f"{API}/health/ready", timeout=10.0)
    print("GET /health/ready status", code)
    print("GET /health/ready body", body)
    if code != 200:
        raise SystemExit("STOP: /health/ready not 200 — no writes")
    parsed = json.loads(body)
    if parsed.get("database") != "cip_test":
        raise SystemExit(f"STOP: database={parsed.get('database')!r} (want cip_test) — no writes")
    return parsed


def q(session: Session, sql: str, label: str, params: dict | None = None) -> list:
    dbn = session.execute(text("SELECT current_database()")).scalar()
    print(f"--- {label} ---")
    print("current_database()", dbn)
    if dbn != "cip_test":
        raise SystemExit(f"STOP: SQL current_database()={dbn!r} — no writes")
    print(sql)
    rows = session.execute(text(sql), params or {}).fetchall()
    for row in rows:
        print(tuple(row))
    if not rows:
        print("(no rows)")
    print()
    return list(rows)


def login_admin() -> str:
    code, body = http_json(
        "POST",
        f"{API}/api/v1/auth/login",
        {"email": "admin@local", "password": "changeme"},
    )
    print("POST /auth/login status", code)
    if code != 200:
        raise SystemExit(f"login failed: {body[:500]}")
    token = json.loads(body).get("token")
    if not isinstance(token, str) or not token:
        raise SystemExit("login missing token")
    return token


def build_hl_workbook_bytes() -> bytes:
    data_lineup = pd.DataFrame(
        [
            {
                "Customer": "CUST-HL-01",
                "Distributor": "DIST-HL-01",
                "Channel": "RET",
                "Period": "2026-04-01",
                "SKU": "SKU-HL-01",
                "Qty": "12",
                "MSRP": "100",
                "Promo Price": "90",
                "Disti Margin": "8",
                "Notes": "SESSION E valid row",
            },
        ]
    )
    summary = pd.DataFrame([{"Some": "summary"}])
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        data_lineup.to_excel(writer, sheet_name="Historical Lineup Apr", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
    return bio.getvalue()


def build_shipment_csv_bytes() -> bytes:
    # Minimal XXOMRPT0025-style shipped row (detect_report_type columns).
    csv = (
        "Operating Unit,Bill To,Ship To,Delivery No,Invoice Line,Sales Model Name,Item,Quantity,Ship Confirm Date\n"
        f"ORG-SE,{STAMP}-DIST,{STAMP}-SHIP,D001,1,Model-SE,{STAMP}-SKU,10,2026-08-15\n"
    )
    return csv.encode("utf-8")


def seed_hl_dimensions(session: Session) -> int:
    _seed_import_core(session)
    ch = session.scalar(select(DimChannel).where(DimChannel.code == "RET"))
    if not ch:
        ch = DimChannel(code="RET", name="Retail")
        session.add(ch)
        session.flush()
    if not session.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-HL-01")):
        session.add(DimDistributor(code="DIST-HL-01", name="Dist HL"))
    if not session.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-HL-01")):
        session.add(DimCustomer(code="CUST-HL-01", name="Cust HL", channel_id=ch.id))
    if not session.scalar(select(DimProduct).where(DimProduct.sku == "SKU-HL-01")):
        session.add(DimProduct(sku="SKU-HL-01", name="Hist Product", category="Audio"))
    src = session.scalar(select(SourceDefinition).where(SourceDefinition.code == "historical_lineup_default"))
    if src is None:
        raise SystemExit("historical_lineup_default source missing on cip_test")
    session.commit()
    return int(src.id)


def create_validated_hl_job(session: Session, source_id: int) -> int:
    workbook = build_hl_workbook_bytes()
    HL_FIXTURE.write_bytes(workbook)
    storage = get_storage_backend()
    job = ImportJob(
        source_id=source_id,
        template_slug="historical_lineup",
        import_mode="validate",
        status="pending",
        stage="uploaded",
        file_name="session_e_hl_fixture.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    session.add(job)
    session.flush()
    key = f"imports/test/{job.id}/session_e_hl_fixture.xlsx"
    storage.save(key, workbook, job.content_type)
    session.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
    session.commit()
    processed = process_import_job_sync(session, job.id)
    print("HL job processed id", processed.id, "stage", processed.stage, "status", processed.status)
    q(
        session,
        "SELECT id, template_slug, stage, status, import_mode FROM import_job WHERE id = :id",
        "HL job after validate",
        {"id": int(processed.id)},
    )
    return int(processed.id)


def seed_shipment_product(session: Session) -> None:
    if not session.scalar(select(DimProduct).where(DimProduct.sku == f"{STAMP}-SKU")):
        session.add(DimProduct(sku=f"{STAMP}-SKU", name="SESSION E Shipment SKU", category="Test"))
        session.commit()


def create_validated_shipment_job(session: Session) -> int:
    src = session.scalar(select(SourceDefinition).where(SourceDefinition.code == "inbound_default"))
    if src is None:
        src = session.scalar(select(SourceDefinition).limit(1))
    if src is None:
        raise SystemExit("no source_definition on cip_test")
    raw = build_shipment_csv_bytes()
    SHIP_FIXTURE.write_bytes(raw)
    storage = get_storage_backend()
    job = ImportJob(
        source_id=int(src.id),
        template_slug="inbound_shipments",
        import_mode="validate",
        status="pending",
        stage="uploaded",
        file_name="session_e_shipment_fixture.csv",
        content_type="text/csv",
    )
    session.add(job)
    session.flush()
    key = f"imports/test/{job.id}/session_e_shipment_fixture.csv"
    storage.save(key, raw, job.content_type)
    session.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(raw), checksum=None))
    session.commit()
    processed = process_import_job_sync(session, job.id)
    print("Shipment job processed id", processed.id, "stage", processed.stage, "status", processed.status)
    q(
        session,
        "SELECT id, template_slug, stage, status, import_mode FROM import_job WHERE id = :id",
        "Shipment job after validate",
        {"id": int(processed.id)},
    )
    q(
        session,
        "SELECT count(*) FROM shipment_evidence_line WHERE import_job_id = :id",
        "Shipment evidence lines",
        {"id": int(processed.id)},
    )
    q(
        session,
        "SELECT count(*) FROM import_entity_mapping_candidate WHERE import_job_id = :id",
        "Shipment mapping candidates",
        {"id": int(processed.id)},
    )
    return int(processed.id)


def poll_progress(job_id: int, token: str, label: str, max_wait: float = 90.0) -> dict | None:
    deadline = time.time() + max_wait
    last: dict | None = None
    while time.time() < deadline:
        code, body = http_json("GET", f"{API}/api/v1/imports/jobs/{job_id}/dsi-progress", token=token)
        print(f"{label} GET dsi-progress status", code)
        print(body[:2000])
        if code == 200:
            last = json.loads(body)
            phase = (last or {}).get("phase") or (last or {}).get("status")
            pct = (last or {}).get("pct")
            if phase in ("done", "complete", "failed", "error") or pct == 100:
                return last
            if (last or {}).get("complete") is True:
                return last
        time.sleep(2)
    return last


def main() -> int:
    print("=== SESSION E cip_test walk ===\n")
    require_cip_test_api()

    sync = get_settings().database_url_sync
    target = sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test"))
    engine = create_engine(target)

    hl_job_id: int | None = None
    ship_job_id: int | None = None

    with Session(engine) as session:
        q(session, "SELECT current_database()", "pre-seed")
        source_id = seed_hl_dimensions(session)
        seed_shipment_product(session)
        hl_job_id = create_validated_hl_job(session, source_id)
        ship_job_id = create_validated_shipment_job(session)

    token = login_admin()

    print("--- POST shipment apply ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/shipment-evidence/jobs/{ship_job_id}/apply",
        {},
        token=token,
    )
    print("status", code)
    print(body[:4000])
    apply_payload = json.loads(body) if code in (200, 202) else {}
    print()

    with Session(engine) as session:
        q(
            session,
            "SELECT id, stage, status, import_mode FROM import_job WHERE id = :id",
            "Shipment job after apply dispatch",
            {"id": ship_job_id},
        )

    if apply_payload.get("async"):
        print("--- Poll dsi-progress (S11) ---")
        progress = poll_progress(int(ship_job_id), token, "S11")
        print("final progress", json.dumps(progress, default=str)[:2000])
        print()

    with Session(engine) as session:
        q(
            session,
            "SELECT id, stage, status, import_mode FROM import_job WHERE id = :id",
            "Shipment job after apply complete",
            {"id": ship_job_id},
        )
        q(
            session,
            "SELECT count(*) FROM fact_inbound_shipment WHERE source_key LIKE :pfx",
            "fact_inbound_shipment rows for SESSION E",
            {"pfx": f"%{STAMP}%"},
        )

    print("HL_JOB_ID", hl_job_id)
    print("SHIPMENT_JOB_ID", ship_job_id)
    print("HL_FIXTURE_PATH", HL_FIXTURE)
    print("SHIP_FIXTURE_PATH", SHIP_FIXTURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

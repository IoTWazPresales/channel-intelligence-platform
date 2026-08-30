"""SESSION D unit 6f write-path on cip_test.

STOP if GET /health/ready is not database=cip_test. No writes in that case.
SQL uses a rewritten sync URL to cip_test and prints current_database() on
every query. HTTP writes go to the running API on :8001.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from app.models.commercial_lineup import (  # noqa: E402
    CommercialLineupCase,
    CommercialLineupLine,
)
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct  # noqa: E402
from app.models.facts import FactInboundShipment  # noqa: E402

API = "http://127.0.0.1:8001"
ACCEPT_TOKEN = "SESSION-D-ACCEPT"
CLEAR_TOKEN = "SESSION-D-CLEAR"
CONFLICT_TOKEN = "SESSION-D-CONFLICT"
SKU_ACCEPT = "SESSIOND-P-ACCEPT"
SKU_CLEAR = "SESSIOND-P-CLEAR"
SKU_CONFLICT = "SESSIOND-P-CONFLICT"
CODE_A = "SESSIOND-DA"
CODE_B = "SESSIOND-DB"
CODE_C = "SESSIOND-DC"


def rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 30.0):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, body
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
    db = parsed.get("database")
    if db != "cip_test":
        raise SystemExit(f"STOP: /health/ready database={db!r} (want cip_test) — no writes")
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


def get_or_create_dist(session: Session, code: str, name: str) -> DimDistributor:
    row = session.scalar(select(DimDistributor).where(DimDistributor.code == code))
    if row:
        return row
    row = DimDistributor(code=code, name=name, tenant_id="default", distributor_status="active")
    session.add(row)
    session.flush()
    return row


def get_or_create_product(session: Session, sku: str, name: str) -> DimProduct:
    row = session.scalar(select(DimProduct).where(DimProduct.sku == sku))
    if row:
        return row
    row = DimProduct(sku=sku, name=name, tenant_id="default", is_active=True)
    session.add(row)
    session.flush()
    return row


def seed(session: Session) -> dict[str, int]:
    dbn = session.execute(text("SELECT current_database()")).scalar()
    print("seed current_database()", dbn)
    if dbn != "cip_test":
        raise SystemExit(f"STOP: seed current_database()={dbn!r}")
    oc = session.scalar(select(DimCustomer).where(DimCustomer.code == "OPEN_CHANNEL"))
    if oc is None:
        raise SystemExit("STOP: OPEN_CHANNEL missing on cip_test")
    da = get_or_create_dist(session, CODE_A, "SESSION D Dist A")
    db_ = get_or_create_dist(session, CODE_B, "SESSION D Dist B")
    dc = get_or_create_dist(session, CODE_C, "SESSION D Dist C")
    pa = get_or_create_product(session, SKU_ACCEPT, "SESSION D accept SKU")
    pc = get_or_create_product(session, SKU_CLEAR, "SESSION D clear SKU")
    pf = get_or_create_product(session, SKU_CONFLICT, "SESSION D conflict SKU")
    case = CommercialLineupCase(
        file_name="SESSION-D-UNIT6F",
        period_label="26Q3",
        import_intent="current_working_lineup",
        source_context="commercial_planner",
        commercial_status="draft_imported",
        notes="SESSION D unit 6f disposable seed",
        inferred_period_start=date(2026, 7, 1),
        business_unit="SESSIOND",
    )
    session.add(case)
    session.flush()
    line_accept = CommercialLineupLine(
        case_id=case.id,
        source_row_number=1,
        product_id=pa.id,
        customer_id=oc.id,
        distributor_id=None,
        distributor_attribution_status="token_proposed",
        customer_token=ACCEPT_TOKEN,
        sku_raw=SKU_ACCEPT,
        quantity_units=36,
        row_status="imported",
        raw_row_payload={"session_d": "accept"},
    )
    line_clear = CommercialLineupLine(
        case_id=case.id,
        source_row_number=2,
        product_id=pc.id,
        customer_id=oc.id,
        distributor_id=da.id,
        distributor_attribution_status="token_proposed",
        customer_token=CLEAR_TOKEN,
        sku_raw=SKU_CLEAR,
        quantity_units=10,
        row_status="imported",
        raw_row_payload={"session_d": "soft_clear"},
    )
    line_conflict = CommercialLineupLine(
        case_id=case.id,
        source_row_number=3,
        product_id=pf.id,
        customer_id=oc.id,
        distributor_id=dc.id,
        distributor_attribution_status="token_proposed",
        customer_token=CONFLICT_TOKEN,
        sku_raw=SKU_CONFLICT,
        quantity_units=20,
        row_status="imported",
        raw_row_payload={"session_d": "conflict"},
    )
    session.add_all([line_accept, line_clear, line_conflict])
    session.flush()
    stamp = int(time.time())
    ship_date = date(2026, 8, 15)
    facts = [
        FactInboundShipment(
            source_key=f"session-d-accept-{stamp}",
            fact_upsert_key=f"session-d-accept-{stamp}",
            source_row_number=1,
            report_type="session_d",
            line_state="shipped",
            raw_source_row={"session_d": True},
            quantity=36,
            product_id=pa.id,
            product_resolution_status="resolved",
            distributor_id=da.id,
            resolved_distributor_id=da.id,
            distributor_resolution_status="resolved",
            ship_confirm_date=ship_date,
            status="shipped",
        ),
        FactInboundShipment(
            source_key=f"session-d-conflict-a-{stamp}",
            fact_upsert_key=f"session-d-conflict-a-{stamp}",
            source_row_number=2,
            report_type="session_d",
            line_state="shipped",
            raw_source_row={"session_d": True},
            quantity=20,
            product_id=pf.id,
            product_resolution_status="resolved",
            distributor_id=da.id,
            resolved_distributor_id=da.id,
            distributor_resolution_status="resolved",
            ship_confirm_date=ship_date,
            status="shipped",
        ),
        FactInboundShipment(
            source_key=f"session-d-conflict-b-{stamp}",
            fact_upsert_key=f"session-d-conflict-b-{stamp}",
            source_row_number=3,
            report_type="session_d",
            line_state="shipped",
            raw_source_row={"session_d": True},
            quantity=20,
            product_id=pf.id,
            product_resolution_status="resolved",
            distributor_id=db_.id,
            resolved_distributor_id=db_.id,
            distributor_resolution_status="resolved",
            ship_confirm_date=ship_date,
            status="shipped",
        ),
    ]
    session.add_all(facts)
    session.commit()
    ids = {
        "case_id": int(case.id),
        "line_accept": int(line_accept.id),
        "line_clear": int(line_clear.id),
        "line_conflict": int(line_conflict.id),
        "dist_a": int(da.id),
        "dist_b": int(db_.id),
        "dist_c": int(dc.id),
        "oc": int(oc.id),
    }
    print("seeded", ids)
    return ids


def line_sql(line_ids: list[int]) -> str:
    ids = ",".join(str(i) for i in line_ids)
    return (
        "SELECT id, case_id, distributor_id, distributor_attribution_status, customer_token "
        f"FROM commercial_lineup_line WHERE id IN ({ids}) ORDER BY id"
    )


def audit_sql() -> str:
    return (
        "SELECT id, created_at, actor, action, entity_type, entity_token, target_dim, target_id "
        "FROM steward_audit_event ORDER BY id DESC LIMIT 8"
    )


def main() -> int:
    print("=== SESSION D unit 6f cip_test walk ===\n")
    require_cip_test_api()

    sync = get_settings().database_url_sync
    target = sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test"))
    engine = create_engine(target)

    with Session(engine) as session:
        q(session, "SELECT current_database()", "pre-seed identity")
        q(
            session,
            "SELECT count(*) FROM commercial_lineup_line "
            "WHERE distributor_attribution_status = 'conflict'",
            "pre-seed conflict count",
        )
        ids = seed(session)

    line_ids = [ids["line_accept"], ids["line_clear"], ids["line_conflict"]]

    with Session(engine) as session:
        q(session, line_sql(line_ids), "BEFORE lines")
        q(session, audit_sql(), "BEFORE audit")

    print("--- confirmer preview ACCEPT ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/commercial-planner/lineup/distributor-attribution/confirmer/preview",
        {"norm_tokens": [ACCEPT_TOKEN]},
    )
    print("status", code)
    print(body[:4000])
    print()

    print("--- POST accept-ship ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/commercial-planner/lineup/distributor-attribution/accept-ship",
        {
            "norm_token": ACCEPT_TOKEN,
            "distributor_id": ids["dist_a"],
            "reason": "SESSION D unit 6f accept-ship evidence",
        },
    )
    print("status", code)
    print(body[:4000])
    print()
    if code != 200:
        raise SystemExit(f"accept-ship failed HTTP {code}")

    with Session(engine) as session:
        q(session, line_sql([ids["line_accept"]]), "AFTER accept-ship line")
        q(session, audit_sql(), "AFTER accept-ship audit")

    print("--- POST soft-clear ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/commercial-planner/lineup/distributor-attribution/soft-clear",
        {
            "line_ids": [ids["line_clear"]],
            "reason": "SESSION D unit 6f soft-clear evidence",
        },
    )
    print("status", code)
    print(body[:4000])
    print()
    if code != 200:
        raise SystemExit(f"soft-clear failed HTTP {code}")

    with Session(engine) as session:
        q(session, line_sql([ids["line_clear"]]), "AFTER soft-clear line")
        q(session, audit_sql(), "AFTER soft-clear audit")

    print("--- POST confirmer/apply CONFLICT (create conflict, keep dist) ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/commercial-planner/lineup/distributor-attribution/confirmer/apply",
        {"norm_tokens": [CONFLICT_TOKEN]},
    )
    print("status", code)
    print(body[:4000])
    print()
    if code != 200:
        raise SystemExit(f"confirmer apply 1 failed HTTP {code}")

    with Session(engine) as session:
        q(session, line_sql([ids["line_conflict"]]), "AFTER confirmer-1 conflict line")
        q(session, audit_sql(), "AFTER confirmer-1 audit")

    print("--- POST confirmer/apply CONFLICT again (no auto-clear) ---")
    code, body = http_json(
        "POST",
        f"{API}/api/v1/commercial-planner/lineup/distributor-attribution/confirmer/apply",
        {"norm_tokens": [CONFLICT_TOKEN]},
    )
    print("status", code)
    print(body[:4000])
    print()
    if code != 200:
        raise SystemExit(f"confirmer apply 2 failed HTTP {code}")

    with Session(engine) as session:
        q(session, line_sql(line_ids), "AFTER confirmer-2 all seed lines")
        q(session, audit_sql(), "AFTER confirmer-2 audit")
        q(
            session,
            "SELECT count(*) FROM commercial_lineup_line "
            "WHERE distributor_attribution_status = 'conflict'",
            "post-walk conflict count",
        )

    print("=== walk complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only queries for VERIFY browser evidence session."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


def rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def engine_for(dbname: str):
    sync = get_settings().database_url_sync
    return create_engine(sqlalchemy_sync_engine_url(rewrite_dbname(sync, dbname)))


def q(session: Session, label: str, sql: str) -> None:
    dbn = session.execute(text("SELECT current_database()")).scalar()
    print(f"--- {label} ---")
    print("current_database()", dbn)
    rows = session.execute(text(sql)).fetchall()
    for row in rows:
        print(tuple(row))
    if not rows:
        print("(no rows)")
    print()


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_browser_query.py <health|lines|audit|forecasts>")
        return 2
    cmd = sys.argv[1]
    if cmd == "health":
        with urllib.request.urlopen("http://127.0.0.1:8001/health/ready", timeout=10) as r:
            print(r.read().decode())
        return 0
    if cmd == "review":
        url = (
            "http://127.0.0.1:8001/api/v1/commercial-planner/lineup/"
            "distributor-attribution/review?limit=10&status=token_proposed"
        )
        with urllib.request.urlopen(url, timeout=15) as r:
            print(r.read().decode()[:4000])
        return 0
    if cmd == "worklist":
        url = (
            "http://127.0.0.1:8001/api/v1/commercial-planner/lineup/"
            "customer-token/worklist?limit=50"
        )
        with urllib.request.urlopen(url, timeout=15) as r:
            print(r.read().decode()[:4000])
        return 0
    if cmd == "profile":
        with urllib.request.urlopen(
            "http://127.0.0.1:8001/api/v1/auth/tenant-commercial-profile", timeout=15
        ) as r:
            print(r.read().decode()[:4000])
        return 0
    if cmd == "profile_file":
        from app.services import commercial_tenant_profile as profile  # noqa: E402

        path = profile._tenant_profile_override_path("default")
        print("tenant_profile_path", path)
        if path.is_file():
            print(path.read_text(encoding="utf-8")[:4000])
        else:
            print("(file missing)")
        return 0
    db = "cip_test" if cmd != "cip" else "cip"
    with Session(engine_for(db)) as session:
        if cmd == "lines":
            q(
                session,
                "seed lines",
                "SELECT id, case_id, distributor_id, distributor_attribution_status, customer_token "
                "FROM commercial_lineup_line WHERE customer_token LIKE 'SESSION-D-%' ORDER BY id",
            )
        elif cmd == "audit":
            q(
                session,
                "audit tail",
                "SELECT id, created_at, actor, action, entity_type, entity_token, target_dim, target_id "
                "FROM steward_audit_event ORDER BY id DESC LIMIT 10",
            )
        elif cmd == "forecasts":
            q(session, "null tenant", "SELECT count(*) FROM fact_demand_forecast WHERE tenant_id IS NULL")
            q(
                session,
                "sample forecasts",
                "SELECT id, tenant_id, method, velocity_basis, analogue_basis "
                "FROM fact_demand_forecast ORDER BY id DESC LIMIT 5",
            )
        elif cmd == "cpor":
            q(
                session,
                "cpor cases",
                "SELECT id, case_code, status FROM cpor_case ORDER BY id DESC LIMIT 5",
            )
            q(
                session,
                "cpor lines",
                "SELECT case_id, id, product_id, estimate_qty FROM cpor_case_line ORDER BY case_id, id LIMIT 10",
            )
        else:
            print("unknown", cmd)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

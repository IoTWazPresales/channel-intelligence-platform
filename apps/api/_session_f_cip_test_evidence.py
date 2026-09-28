"""SESSION F cip_test evidence — disposable run script."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(API_ROOT))


def _set_db_in_url(url: str | None, dbname: str) -> str | None:
    if not url:
        return url
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def _load_cip_test_env() -> None:
    env_file = API_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    for key in (
        "DATABASE_URL_SYNC",
        "DATABASE_URL_SYNC_MIGRATE",
        "DATABASE_URL",
        "DATABASE_URL_LOCAL_SYNC",
        "DATABASE_URL_LOCAL",
    ):
        if key in os.environ and os.environ[key]:
            os.environ[key] = _set_db_in_url(os.environ[key], "cip_test") or os.environ[key]


_load_cip_test_env()

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints.cpor_cases import _generate_case_code  # noqa: E402
from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.commercial_tenant_profile import lineup_export_columns  # noqa: E402
from app.services.cpor.cost_suggestion import resolve_default_margin, suggest_cost_basis  # noqa: E402
from app.services.cpor.promo_plan_builder import create_case_from_promo_draft  # noqa: E402
from app.services.cpor.recompute import recompute_case_line  # noqa: E402


def run_query(session, sql: str, label: str | None = None) -> None:
    if label:
        print(f"--- {label} ---")
    print(sql)
    rows = session.execute(text(sql)).fetchall()
    for row in rows:
        print(row)
    if not rows:
        print("(no rows)")
    print()


def main() -> None:
    print("=== SESSION F cip_test evidence ===\n")

    with SessionLocal() as session:
        run_query(session, "SELECT current_database()", "1")
        run_query(session, "SELECT count(*) FROM fact_demand_forecast WHERE tenant_id IS NULL", "2")
        run_query(
            session,
            "SELECT id, tenant_id, method, velocity_basis, analogue_basis FROM fact_demand_forecast LIMIT 3",
            "3",
        )
        run_query(session, "SELECT count(*) FROM fact_sales_sellout", "4")
        run_query(session, "SELECT count(*) FROM fact_customer_velocity", "5")

    print("--- 6 alembic current on cip_test ---")
    env = os.environ.copy()
    migrate = env.get("DATABASE_URL_SYNC_MIGRATE") or env.get("DATABASE_URL_SYNC")
    if migrate:
        env["DATABASE_URL_SYNC_MIGRATE"] = migrate
        env["DATABASE_URL_SYNC"] = migrate
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=str(API_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    print(proc.stdout, end="")
    print(proc.stderr, end="")
    print(f"exit_code={proc.returncode}\n")

    print("=== B4 create_case_from_promo_draft on cip_test ===\n")
    with SessionLocal() as session:
        run_query(session, "SELECT count(*) FROM cpor_case", "B4 cpor_case count BEFORE")
        run_query(session, "SELECT count(*) FROM cpor_case_line", "B4 cpor_case_line count BEFORE")

        seed_id = session.execute(
            text("SELECT id FROM cpor_case ORDER BY id LIMIT 1")
        ).scalar()
        if seed_id is None:
            from datetime import date

            from app.models.cpor import CporCase

            customer_id = session.execute(
                text("SELECT id FROM dim_customer ORDER BY id LIMIT 1")
            ).scalar()
            if customer_id is None:
                raise SystemExit("No dim_customer on cip_test for B4 seed")
            seed = CporCase(
                case_code="C-SESSION-F-SEED",
                case_name="SESSION F B4 seed",
                tenant_id="default",
                customer_id=int(customer_id),
                promotion_type="instant_rebate",
                window_start=date(2026, 4, 1),
                window_end=date(2026, 6, 30),
                status="draft",
                roe_snapshot=18.5,
                currency_code="ZAR",
                channel="reseller",
                created_by="session_f_evidence",
                export_version=1,
                workflow_status="draft",
            )
            session.add(seed)
            session.flush()
            seed_id = seed.id
            session.commit()
            print(f"Created minimal seed cpor_case id={seed_id}")
            print()
        products = session.execute(text("SELECT id FROM dim_product ORDER BY id LIMIT 2")).scalars().all()
        if len(products) < 2:
            raise SystemExit("Need at least 2 dim_product rows on cip_test")
        dist_id = session.execute(
            text(
                "SELECT distributor_id FROM cpor_case_line WHERE distributor_id IS NOT NULL "
                "ORDER BY id LIMIT 1"
            )
        ).scalar()
        if dist_id is None:
            dist_id = session.execute(text("SELECT id FROM dim_distributor ORDER BY id LIMIT 1")).scalar()
        if dist_id is None:
            dist_id = None

        def record_event(_session, **kwargs):
            pass

        out = create_case_from_promo_draft(
            session,
            seed_case_id=int(seed_id),
            confirm_over_budget=True,
            actor="session_f_evidence",
            lines=[
                {
                    "product_id": int(products[0]),
                    "distributor_id": int(dist_id) if dist_id is not None else None,
                    "srp": 19999.0,
                    "estimate_qty": 40.0,
                    "cost_basis": 18.0,
                    "pod_quarter": "26Q2",
                    "dirty_fields": ["cost_basis"],
                },
                {
                    "product_id": int(products[1]),
                    "distributor_id": int(dist_id) if dist_id is not None else None,
                    "srp": 8999.0,
                    "estimate_qty": 22.0,
                    "cost_basis": None,
                    "pod_quarter": "26Q2",
                    "dirty_fields": [],
                },
            ],
            generate_case_code=_generate_case_code,
            record_event=record_event,
            recompute_case_line=recompute_case_line,
            resolve_default_margin=resolve_default_margin,
            suggest_cost_basis=suggest_cost_basis,
        )
        session.commit()
        new_case_id = out.get("case_id") or out.get("id")
        if new_case_id is None and "case" in out:
            new_case_id = out["case"].get("id")
        print("create_case_from_promo_draft result:")
        print(out)
        print()

        run_query(session, "SELECT count(*) FROM cpor_case", "B4 cpor_case count AFTER")
        run_query(session, "SELECT count(*) FROM cpor_case_line", "B4 cpor_case_line count AFTER")
        run_query(
            session,
            f"SELECT id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
            f"WHERE case_id = {int(new_case_id)} ORDER BY id",
            f"B4 lines for case_id={new_case_id} (id column; no line_id in schema)",
        )
        try:
            run_query(
                session,
                f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
                f"WHERE case_id = {int(new_case_id)} ORDER BY line_id",
                f"User-requested SQL line_id for case_id={new_case_id}",
            )
        except Exception as exc:
            print(f"--- User-requested SQL line_id for case_id={new_case_id} ---")
            print(
                f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
                f"WHERE case_id = {int(new_case_id)} ORDER BY line_id"
            )
            print(exc)
            print()

    print("=== D-056 lineup_export_columns('default') ===\n")
    cols = lineup_export_columns("default")
    for pair in cols:
        print(pair)


if __name__ == "__main__":
    main()

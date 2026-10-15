"""NS-4 settle confirm path — end-to-end on disposable clone DB (never cip).

Exercises preview (settlement consolidation) → readiness → FX gate → transition handler.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

# N-0096: this ran on a named disposable clone (cip_ns4_settle_clone) that no longer exists, and its
# fixture rewrote os.environ without restoring it, so every later DB test failed. It now runs on the
# database the suite points at (cip_test), seeds its own two ended cases and deletes them again.
# It never runs on cip.


def _assert_not_cip(url: str) -> None:
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    assert db_name != "cip", f"Refusing writes against cip (url={url})"


def _settle_url_sync() -> str:
    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    return sqlalchemy_sync_engine_url(get_settings().database_url_sync)


@pytest.fixture(scope="module")
def settle_smoke_env():
    url = _settle_url_sync()
    _assert_not_cip(url)
    with create_engine(url).connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        if db != "cip_test":
            pytest.skip(f"settle confirm test runs on cip_test only (database is {db})")
        fx_col = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'cpor_case' AND column_name = 'fx_mode'
                """
            )
        ).first()
        if fx_col is None:
            pytest.skip("cpor_case.fx_mode missing: cip_test is behind the migrations")
        if conn.execute(text("SELECT 1 FROM dim_customer LIMIT 1")).first() is None:
            pytest.skip("cip_test has no dim_customer row to hang a case on")
    yield


def _unique_code(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def _insert_ended_case(*, fx_mode: str | None, roe: Decimal | None) -> int:
    from app.db.session_sync import SessionLocal
    from app.models.cpor import CporCase
    from app.models.dimensions import DimCustomer

    with SessionLocal() as session:
        customer_id = session.scalar(select(DimCustomer.id).limit(1))
        assert customer_id is not None, "dim_customer empty on clone — cannot seed settle case"
        case = CporCase(
            case_code=_unique_code("NS4SET"),
            customer_id=int(customer_id),
            promotion_type="Sell out PP",
            window_start=date(2026, 1, 1),
            window_end=date(2026, 1, 31),
            status="ended",
            workflow_status="ended",
            roe_snapshot=roe,
            fx_mode=fx_mode,
            currency_code="ZAR",
            channel="reseller",
            created_by="settle_clone_test",
        )
        session.add(case)
        session.commit()
        session.refresh(case)
        return int(case.id)


def _count_settled() -> int:
    with create_engine(_settle_url_sync()).connect() as conn:
        return int(
            conn.execute(text("SELECT count(*) FROM cpor_case WHERE status = 'settled'")).scalar_one()
        )


def _delete_case(case_id: int) -> None:
    from app.db.session_sync import SessionLocal
    from app.models.cpor import CporCase, CporCaseEvent
    from sqlalchemy import delete

    with SessionLocal() as session:
        session.execute(delete(CporCaseEvent).where(CporCaseEvent.case_id == case_id))
        session.execute(delete(CporCase).where(CporCase.id == case_id))
        session.commit()


def test_settle_confirm_path_blocked_and_allowed_on_clone(settle_smoke_env):
    from app.main import app

    client = TestClient(app)
    settled_before = _count_settled()
    print(f"settled_cases_before={settled_before}")

    blocked_id = _insert_ended_case(fx_mode=None, roe=Decimal("18.5"))
    allowed_id = _insert_ended_case(fx_mode="booked", roe=Decimal("18.5"))

    try:
        preview_blocked = client.get(f"/api/v1/cpor/cases/{blocked_id}/settlement")
        assert preview_blocked.status_code == 200, preview_blocked.text
        blocked_body = preview_blocked.json()
        assert blocked_body["can_settle"] is True
        assert blocked_body["claim_row_count"] == 0
        readiness = blocked_body["settle_readiness"]
        assert readiness["fx_settle_allowed"] is False
        assert readiness["claim_evidence_count"] == 0

        blocked_transition = client.post(
            f"/api/v1/cpor/cases/{blocked_id}/transition",
            json={"action": "settle"},
            headers={"X-User-Id": "settle_clone_test"},
        )
        assert blocked_transition.status_code == 409, blocked_transition.text
        detail = blocked_transition.json()["detail"]
        assert detail["code"] == "fx_blocked"

        preview_allowed = client.get(f"/api/v1/cpor/cases/{allowed_id}/settlement")
        assert preview_allowed.status_code == 200, preview_allowed.text
        allowed_body = preview_allowed.json()
        allowed_readiness = allowed_body["settle_readiness"]
        assert allowed_readiness["fx_settle_allowed"] is True
        assert "booked" in (allowed_readiness.get("fx_basis_line") or "")

        allowed_transition = client.post(
            f"/api/v1/cpor/cases/{allowed_id}/transition",
            json={"action": "settle"},
            headers={"X-User-Id": "settle_clone_test"},
        )
        assert allowed_transition.status_code == 200, allowed_transition.text
        settled_case = allowed_transition.json()
        assert settled_case["status"] == "settled"
        assert settled_case["id"] == allowed_id

        settled_after = _count_settled()
        print(f"settled_cases_after={settled_after}")
        assert settled_after == settled_before + 1

        still_blocked = client.get(f"/api/v1/cpor/cases/{blocked_id}")
        assert still_blocked.json()["status"] == "ended"
    finally:
        _delete_case(blocked_id)
        _delete_case(allowed_id)
        settled_cleanup = _count_settled()
        print(f"settled_cases_after_cleanup={settled_cleanup}")
        assert settled_cleanup == settled_before

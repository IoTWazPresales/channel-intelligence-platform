"""BACKLOG-061 B1 — customer promote-in-place unit tests (no cip writes)."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.customer_promote import (
    BULK_UPSERT_TMP_DUPLICATE_WARNING,
    PROMOTE_TARGET_STATUS,
    PROVISIONAL_REUSE_STOP_WARNING,
    CustomerPromoteError,
    _eligibility,
    confirm_customer_promote,
    preview_customer_promote,
)
from app.services.imports import provisional_entity_identity as pei
from app.services.imports.provisional_entity_identity import pick_provisional_customer_for_reuse

client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-CUST-ABC",
        name="Acme",
        customer_status="unverified",
        merged_into_customer_id=None,
        notes_summary=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_with(row, owner=None):
    db = AsyncMock()
    db.get = AsyncMock(return_value=row)

    async def _exec(_stmt):
        result = MagicMock()
        result.scalars.return_value.first.return_value = owner
        return result

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def test_eligibility_tmp_unverified():
    e = _eligibility(_row())
    assert e["eligible"] is True
    assert e["admin_mint_edge"] is False


def test_eligibility_tmp_active_admin_edge():
    e = _eligibility(_row(customer_status="active"))
    assert e["eligible"] is True
    assert e["admin_mint_edge"] is True


def test_eligibility_rejects_non_tmp_and_merged():
    e1 = _eligibility(_row(code="CUST-1"))
    assert e1["eligible"] is False
    assert "code_not_tmp_cust" in e1["reasons"]
    e2 = _eligibility(_row(merged_into_customer_id=99))
    assert e2["eligible"] is False
    assert "row_is_merged_loser" in e2["reasons"]


def test_reuse_sql_gate_excludes_promoted():
    src = inspect.getsource(pei.find_existing_provisional_customer_by_canonical_name)
    assert "TMP-CUST-%" in src
    assert "unverified" in src
    assert pick_provisional_customer_for_reuse("Acme Retail", []) is None


def test_preview_happy_path_warnings_no_write():
    row = _row()
    out = asyncio.run(preview_customer_promote(_db_with(row), customer_id=10, new_code="ACME-001"))
    assert out["dry_run"] is True
    assert out["applied"] is False
    assert out["can_confirm"] is True
    assert PROVISIONAL_REUSE_STOP_WARNING in out["warnings"]
    assert BULK_UPSERT_TMP_DUPLICATE_WARNING in out["warnings"]
    assert row.code == "TMP-CUST-ABC"


def test_preview_collision_with_live_row():
    row = _row()
    other = _row(id=20, code="ACME-001", customer_status="active")
    out = asyncio.run(preview_customer_promote(_db_with(row, other), customer_id=10, new_code="ACME-001"))
    assert out["can_confirm"] is False
    assert out["collision"]["customer_id"] == 20


def test_preview_collision_with_merged_row_still_blocks():
    """UNIQUE code: merged losers retain codes — collision still blocks."""
    row = _row()
    other = _row(id=20, code="ACME-001", customer_status="merged", merged_into_customer_id=1)
    out = asyncio.run(preview_customer_promote(_db_with(row, other), customer_id=10, new_code="ACME-001"))
    assert out["can_confirm"] is False
    assert out["collision"] is not None


def test_confirm_happy_path():
    row = _row()
    db = _db_with(row)
    out = asyncio.run(confirm_customer_promote(db, customer_id=10, new_code="ACME-001", note="steward ok"))
    assert out["applied"] is True
    assert out["customer_id"] == 10
    assert out["old_code"] == "TMP-CUST-ABC"
    assert out["new_code"] == "ACME-001"
    assert out["old_status"] == "unverified"
    assert out["new_status"] == PROMOTE_TARGET_STATUS
    assert out["merged_into_customer_id"] is None
    assert row.code == "ACME-001"
    assert row.customer_status == "active"
    assert row.merged_into_customer_id is None
    db.commit.assert_awaited()


def test_confirm_rejects_without_eligibility():
    row = _row(code="REAL-1", customer_status="active")
    try:
        asyncio.run(confirm_customer_promote(_db_with(row), customer_id=10, new_code="ACME-001"))
        raise AssertionError("expected CustomerPromoteError")
    except CustomerPromoteError as ei:
        assert ei.status_code == 422
    assert row.code == "REAL-1"


def test_confirm_second_time_rejects():
    row = _row(code="ACME-001", customer_status="active")
    try:
        asyncio.run(confirm_customer_promote(_db_with(row), customer_id=10, new_code="ACME-002"))
        raise AssertionError("expected CustomerPromoteError")
    except CustomerPromoteError as ei:
        assert ei.code in ("not_eligible", "already_promoted")


def test_http_preview_and_confirm_gate():
    row = _row()

    async def fake_db():
        yield _db_with(row)

    app.dependency_overrides[get_db] = fake_db

    r = client.post("/api/v1/customers/10/promote", json={"new_code": "ACME-001", "confirm": False})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["applied"] is False
    assert PROVISIONAL_REUSE_STOP_WARNING in body["warnings"]

    r2 = client.post(
        "/api/v1/customers/10/promote",
        json={"new_code": "ACME-001", "confirm": True, "note": "ok"},
    )
    assert r2.status_code == 200
    assert r2.json()["applied"] is True
    assert r2.json()["new_code"] == "ACME-001"

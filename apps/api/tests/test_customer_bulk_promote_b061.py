"""BACKLOG-061 BP1 — bulk customer promote (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.customer_bulk_promote import BATCH_MAX_ROWS, run_customer_bulk_promote
from app.services.customer_promote import PROMOTE_TARGET_STATUS

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


def _db_for_batch(rows_by_code: dict[str, SimpleNamespace], owners_by_new: dict[str, SimpleNamespace] | None = None):
    """Mock AsyncSession: resolve TMP by lower(code); get by id; collision by new code."""
    owners_by_new = owners_by_new or {}
    by_id = {int(r.id): r for r in rows_by_code.values()}
    db = AsyncMock()

    async def _get(_cls, pk):
        return by_id.get(int(pk))

    db.get = AsyncMock(side_effect=_get)

    async def _exec(stmt):
        result = MagicMock()
        key = None
        try:
            for v in stmt.compile().params.values():
                if isinstance(v, str):
                    key = v.lower()
                    break
        except Exception:
            key = None

        found = None
        if key:
            if key.startswith("tmp-cust-"):
                for code, row in rows_by_code.items():
                    if code.lower() == key:
                        found = row
                        break
            else:
                for code, row in owners_by_new.items():
                    if code.lower() == key:
                        found = row
                        break
        result.scalars.return_value.first.return_value = found
        return result

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def test_dry_run_ready_and_blank_skipped():
    row = _row()
    db = _db_for_batch({"TMP-CUST-ABC": row})
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-CUST-ABC", "new_code": "ACME-001"},
                {"tmp_code": "TMP-CUST-ABC", "new_code": ""},  # will also dup-block first? same tmp twice
            ],
            dry_run=True,
        )
    )
    # Same tmp twice → both blocked as intra_batch_duplicate_tmp
    assert out["summary"]["blocked"] == 2


def test_dry_run_mixed_ready_blank_not_found():
    row = _row()
    db = _db_for_batch({"TMP-CUST-ABC": row})
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-CUST-ABC", "new_code": "ACME-001"},
                {"tmp_code": "TMP-CUST-ZZZ", "new_code": "ZZZ-1"},
                {"tmp_code": "TMP-CUST-NOPE", "new_code": ""},
            ],
            dry_run=True,
        )
    )
    assert out["summary"]["ready"] == 1
    assert out["summary"]["blocked"] == 1
    assert out["summary"]["skipped"] == 1
    assert out["rows"][0]["status"] == "ready"
    assert out["rows"][1]["status"] == "blocked"
    assert "tmp_code_not_found" in out["rows"][1]["reasons"]
    assert out["rows"][2]["status"] == "skipped_blank"
    assert row.code == "TMP-CUST-ABC"


def test_intra_batch_duplicate_new_blocks_both():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B")
    db = _db_for_batch({"TMP-CUST-A": a, "TMP-CUST-B": b})
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-CUST-A", "new_code": "SAME"},
                {"tmp_code": "TMP-CUST-B", "new_code": "same"},
            ],
            dry_run=True,
        )
    )
    assert out["summary"]["blocked"] == 2
    assert all("intra_batch_duplicate_new" in r["reasons"] for r in out["rows"])


def test_new_code_tmp_rejected():
    row = _row()
    db = _db_for_batch({"TMP-CUST-ABC": row})
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[{"tmp_code": "TMP-CUST-ABC", "new_code": "TMP-CUST-NEW"}],
            dry_run=True,
        )
    )
    assert out["rows"][0]["status"] == "blocked"
    assert "new_code_is_tmp" in out["rows"][0]["reasons"]


def test_confirm_partial_success():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B")
    owner = _row(id=99, code="TAKEN", customer_status="active")
    db = _db_for_batch(
        {"TMP-CUST-A": a, "TMP-CUST-B": b},
        owners_by_new={"TAKEN": owner},
    )
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-CUST-A", "new_code": "FREE-1", "note": "ok"},
                {"tmp_code": "TMP-CUST-B", "new_code": "TAKEN"},
            ],
            dry_run=False,
        )
    )
    assert out["summary"]["applied"] == 1
    assert out["summary"]["blocked"] == 1
    assert a.code == "FREE-1"
    assert a.customer_status == PROMOTE_TARGET_STATUS
    assert b.code == "TMP-CUST-B"
    assert out["rows"][0]["outcome"] == "applied"
    assert out["rows"][1]["outcome"] == "blocked"


def test_batch_too_large_http():
    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    rows = [{"tmp_code": f"TMP-CUST-{i}", "new_code": f"C-{i}"} for i in range(BATCH_MAX_ROWS + 1)]
    r = client.post("/api/v1/customers/promote/batch", json={"rows": rows, "dry_run": True})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "batch_too_large"


def test_http_dry_run_no_mutate():
    row = _row()

    async def fake_db():
        yield _db_for_batch({"TMP-CUST-ABC": row})

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/customers/promote/batch",
        json={
            "dry_run": True,
            "rows": [{"tmp_code": "tmp-cust-abc", "new_code": "ACME-001"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["summary"]["ready"] == 1
    assert row.code == "TMP-CUST-ABC"

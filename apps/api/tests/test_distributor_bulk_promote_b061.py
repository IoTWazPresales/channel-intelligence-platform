"""BACKLOG-061-U-B3a — bulk distributor promote map mode (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.distributor_bulk_promote import BATCH_MAX_ROWS, run_distributor_bulk_promote
from app.services.distributor_promote import PROMOTE_TARGET_STATUS

client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-DIST-ABC",
        name="Acme Dist",
        distributor_status="active",
        merged_into_distributor_id=None,
        merge_note=None,
        no_code_disposition=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_for_batch(rows_by_code: dict[str, SimpleNamespace], owners_by_new: dict[str, SimpleNamespace] | None = None):
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
            if key.startswith("tmp-dist-"):
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


def test_dry_run_mixed_ready_blank_not_found():
    row = _row()
    db = _db_for_batch({"TMP-DIST-ABC": row})
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-DIST-ABC", "new_code": "ACME-001"},
                {"tmp_code": "TMP-DIST-ZZZ", "new_code": "ZZZ-1"},
                {"tmp_code": "TMP-DIST-NOPE", "new_code": ""},
            ],
            dry_run=True,
        )
    )
    assert out["summary"]["ready"] == 1
    assert out["summary"]["blocked"] == 1
    assert out["summary"]["skipped"] == 1
    assert out["rows"][0]["status"] == "ready"
    assert "tmp_code_not_found" in out["rows"][1]["reasons"]
    assert out["rows"][2]["status"] == "skipped_blank"
    assert row.code == "TMP-DIST-ABC"


def test_intra_batch_duplicate_new_blocks_both():
    a = _row(id=10, code="TMP-DIST-A")
    b = _row(id=11, code="TMP-DIST-B")
    db = _db_for_batch({"TMP-DIST-A": a, "TMP-DIST-B": b})
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-DIST-A", "new_code": "SAME"},
                {"tmp_code": "TMP-DIST-B", "new_code": "same"},
            ],
            dry_run=True,
        )
    )
    assert out["summary"]["blocked"] == 2
    assert all("intra_batch_duplicate_new" in r["reasons"] for r in out["rows"])


def test_new_code_tmp_rejected():
    row = _row()
    db = _db_for_batch({"TMP-DIST-ABC": row})
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[{"tmp_code": "TMP-DIST-ABC", "new_code": "TMP-DIST-NEW"}],
            dry_run=True,
        )
    )
    assert out["rows"][0]["status"] == "blocked"
    assert "new_code_is_tmp" in out["rows"][0]["reasons"]


def test_non_tmp_prefix_rejected():
    row = _row(code="REAL-1")
    db = _db_for_batch({"REAL-1": row})
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[{"tmp_code": "REAL-1", "new_code": "ACME-1"}],
            dry_run=True,
        )
    )
    assert out["rows"][0]["status"] == "blocked"
    assert "tmp_code_not_tmp_dist" in out["rows"][0]["reasons"]


def test_merged_row_blocked():
    row = _row(merged_into_distributor_id=99)
    db = _db_for_batch({"TMP-DIST-ABC": row})
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[{"tmp_code": "TMP-DIST-ABC", "new_code": "ACME-1"}],
            dry_run=True,
        )
    )
    assert out["rows"][0]["status"] == "blocked"
    assert "row_is_merged_loser" in out["rows"][0]["reasons"]


def test_confirm_partial_success():
    a = _row(id=10, code="TMP-DIST-A")
    b = _row(id=11, code="TMP-DIST-B")
    owner = _row(id=99, code="TAKEN", distributor_status="active")
    db = _db_for_batch(
        {"TMP-DIST-A": a, "TMP-DIST-B": b},
        owners_by_new={"TAKEN": owner},
    )
    out = asyncio.run(
        run_distributor_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-DIST-A", "new_code": "FREE-1", "note": "ok"},
                {"tmp_code": "TMP-DIST-B", "new_code": "TAKEN"},
            ],
            dry_run=False,
        )
    )
    assert out["summary"]["applied"] == 1
    assert out["summary"]["blocked"] == 1
    assert a.code == "FREE-1"
    assert a.distributor_status == PROMOTE_TARGET_STATUS
    assert b.code == "TMP-DIST-B"
    assert out["rows"][0]["outcome"] == "applied"
    assert out["rows"][1]["outcome"] == "blocked"


def test_batch_too_large_http():
    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    rows = [{"tmp_code": f"TMP-DIST-{i}", "new_code": f"D-{i}"} for i in range(BATCH_MAX_ROWS + 1)]
    r = client.post("/api/v1/distributors/promote/batch", json={"rows": rows, "dry_run": True})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "batch_too_large"


def test_http_dry_run_no_mutate():
    row = _row()

    async def fake_db():
        yield _db_for_batch({"TMP-DIST-ABC": row})

    app.dependency_overrides[get_db] = fake_db
    r = client.post(
        "/api/v1/distributors/promote/batch",
        json={
            "dry_run": True,
            "rows": [{"tmp_code": "tmp-dist-abc", "new_code": "ACME-001"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["summary"]["ready"] == 1
    assert row.code == "TMP-DIST-ABC"

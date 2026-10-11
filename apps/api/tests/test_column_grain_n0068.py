"""N-0068 / D-0060: per-line PM column sets on the tenant column grain (no DB).

Covers the read/write axis agreement for column_mapping_memory, the tenant grain
lookup, the admin-only column-grain endpoints and the sellable-line check on a
Product Master mapping save. Database-level checks live in
test_column_grain_n0068_db.py (cip_test only).
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.security import Role, get_current_user
from app.main import app
from app.models.product_line_access import TenantColumnGrain
from app.services.imports.pm_mapping_memory import (
    DEFAULT_COLUMN_GRAIN,
    load_by_header_norm,
    merge_memory_from_pm_save,
    tenant_column_grain_sync,
)
from app.services.imports.product_master_workflow import save_mapping_sync, suggest_mapping_decisions

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _stub_user(role: Role = Role.ADMIN):
    async def _fake_user():
        return {"id": "test-user", "role": role, "tenant_id": "default", "email": None, "display_name": None}

    return _fake_user


def _source(memory: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        column_mapping_memory=memory,
        import_template=SimpleNamespace(expected_columns={}),
        expected_template=None,
    )


# --- column_mapping_memory read/write axis ------------------------------------------------


def test_product_line_grain_writes_and_reads_by_product_line() -> None:
    src = _source({"by_header_norm": {"ean": {"target": "barcode_ean", "confirmations": 2}}})
    db = MagicMock()
    db.get.return_value = src
    merge_memory_from_pm_save(
        db,
        source_id=1,
        mapping_decisions={"Chipset": {"target": "model_family"}},
        product_line="MB",
        grain="product_line",
    )
    profile = src.column_mapping_memory["mapping_profile"]
    assert profile["by_product_line"]["MB"]["by_header_norm"]["chipset"]["target"] == "model_family"
    assert "by_grain" not in profile
    mb = load_by_header_norm(src, product_line="MB", grain="product_line")
    assert mb["chipset"]["target"] == "model_family"
    assert mb["ean"]["target"] == "barcode_ean"  # source-wide parity still applies
    nb = load_by_header_norm(src, product_line="NB", grain="product_line")
    assert "chipset" not in nb  # one line's column set does not leak into another


def test_other_grain_writes_by_grain_and_leaves_product_line_sets_alone() -> None:
    src = _source(
        {
            "mapping_profile": {
                "by_product_line": {"NB": {"by_header_norm": {"panel": {"target": "model_family", "confirmations": 1}}}}
            }
        }
    )
    db = MagicMock()
    db.get.return_value = src
    merge_memory_from_pm_save(
        db,
        source_id=1,
        mapping_decisions={"Panel": {"target": "series"}},
        product_line="NB",
        grain="feed",
    )
    profile = src.column_mapping_memory["mapping_profile"]
    assert profile["by_product_line"]["NB"]["by_header_norm"]["panel"]["target"] == "model_family"
    assert profile["by_grain"]["feed"]["NB"]["by_header_norm"]["panel"]["target"] == "series"
    assert load_by_header_norm(src, product_line="NB", grain="feed")["panel"]["target"] == "series"
    assert load_by_header_norm(src, product_line="NB")["panel"]["target"] == "model_family"


def test_suggestions_read_the_axis_the_save_wrote() -> None:
    """G1: before N-0068 the suggest path always read by_product_line."""
    src = _source(
        {
            "mapping_profile": {
                "by_grain": {"feed": {"NB": {"by_header_norm": {"odd_col": {"target": "series", "confirmations": 4}}}}}
            }
        }
    )
    inf = {"columns": [{"name": "odd_col", "dtype": "object", "sample": ["x"]}], "row_count": 1}
    with_grain = suggest_mapping_decisions(["odd_col"], src, inf, product_line="NB", grain="feed")
    assert with_grain["odd_col"]["target"] == "series"
    default_axis = suggest_mapping_decisions(["odd_col"], src, inf, product_line="NB")
    assert default_axis.get("odd_col", {}).get("target") != "series"


# --- tenant grain lookup -------------------------------------------------------------------


def test_tenant_column_grain_defaults_to_product_line() -> None:
    db = MagicMock()
    db.get.return_value = None
    assert tenant_column_grain_sync(db, "default") == DEFAULT_COLUMN_GRAIN == "product_line"
    assert tenant_column_grain_sync(db, None) == "product_line"
    assert tenant_column_grain_sync(db, "  ") == "product_line"
    db.get.return_value = SimpleNamespace(grain="  ")
    assert tenant_column_grain_sync(db, "default") == "product_line"


def test_tenant_column_grain_reads_the_tenant_row() -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(grain="feed")
    assert tenant_column_grain_sync(db, "acme") == "feed"
    db.get.assert_called_once_with(TenantColumnGrain, "acme")


def test_save_mapping_uses_tenant_grain(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.imports.product_master_workflow as wf

    job = SimpleNamespace(
        template_slug="product_master",
        status="draft",
        stage=wf.STAGE_PM_HEADERS,
        file_headers=["id", "title", "brand", "chipset"],
        source_id=7,
        tenant_id="acme",
        mapping_decisions=None,
        field_mapping=None,
        validation_passed=None,
        staged_metadata=None,
        error_summary=None,
    )
    db = MagicMock()

    def _get(model, key):
        if model is TenantColumnGrain:
            return SimpleNamespace(grain="product_line")
        return job

    db.get.side_effect = _get
    seen: dict = {}
    monkeypatch.setattr(wf, "merge_memory_from_pm_save", lambda _db, **kw: seen.update(kw))
    cols = [
        {"header": "id", "target": "technical_product_id"},
        {"header": "title", "target": "display_name"},
        {"header": "brand", "disposition": "ignore"},
        {"header": "chipset", "disposition": "stage_raw"},
    ]
    save_mapping_sync(db, 1, cols, product_line="MB")
    assert seen["product_line"] == "MB"
    assert seen["grain"] == "product_line"
    assert seen["source_id"] == 7


# --- admin-only column-grain endpoints -----------------------------------------------------


def _db_override(row):
    session = MagicMock()
    session.get = AsyncMock(return_value=row)
    session.commit = AsyncMock()
    session.add = MagicMock()

    async def _get_db():
        yield session

    return session, _get_db


def test_column_grain_get_defaults_when_no_row() -> None:
    _, dep = _db_override(None)
    app.dependency_overrides[get_db] = dep
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.get("/api/v1/auth/column-grain")
    assert r.status_code == 200
    assert r.json() == {"tenant_id": "default", "grain": "product_line"}


def test_column_grain_put_normalises_and_saves() -> None:
    row = SimpleNamespace(tenant_id="default", grain="product_line")
    session, dep = _db_override(row)
    app.dependency_overrides[get_db] = dep
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put("/api/v1/auth/column-grain", json={"grain": "  Product_Line "})
    assert r.status_code == 200
    assert r.json()["grain"] == "product_line"
    assert row.grain == "product_line"
    session.commit.assert_awaited()


@pytest.mark.parametrize("grain", ["", "   ", "product line", "1line", "line-code", "a" * 65, "x.y"])
def test_column_grain_put_rejects_non_identifier(grain: str) -> None:
    session, dep = _db_override(None)
    app.dependency_overrides[get_db] = dep
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put("/api/v1/auth/column-grain", json={"grain": grain})
    assert r.status_code == 422
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("role", [Role.STEWARD, Role.PLANNER, Role.VIEWER])
def test_column_grain_routes_are_admin_only(role: Role) -> None:
    session, dep = _db_override(None)
    app.dependency_overrides[get_db] = dep
    app.dependency_overrides[get_current_user] = _stub_user(role)
    assert client.get("/api/v1/auth/column-grain").status_code == 403
    r = client.put("/api/v1/auth/column-grain", json={"grain": "product_line"})
    assert r.status_code == 403
    session.commit.assert_not_awaited()


# --- Product Master mapping save: sellable product line -------------------------------------


@pytest.fixture()
def pm_put(monkeypatch: pytest.MonkeyPatch):
    import app.api.v1.endpoints.imports_product_master as ep

    job = SimpleNamespace(id=1, tenant_id="default", template_slug="product_master", stage="pm_mapping", mapping_decisions={})
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.refresh = AsyncMock()

    async def _get_db():
        yield session

    @contextmanager
    def _fake_session_local():
        yield MagicMock()

    state = {"grain": "product_line", "codes": frozenset({"NB", "MB"}), "saved": []}
    refresh_calls: list[bool] = []

    async def _lines(_db, *, force_refresh: bool = False):
        refresh_calls.append(force_refresh)
        codes = state["codes"]
        return SimpleNamespace(codes=codes, lines=tuple(SimpleNamespace(code=c) for c in sorted(codes)))

    monkeypatch.setattr(ep, "SessionLocal", _fake_session_local)
    monkeypatch.setattr(ep, "tenant_column_grain_sync", lambda _db, _tid: state["grain"])
    monkeypatch.setattr(ep, "list_sellable_product_lines", _lines)
    monkeypatch.setattr(
        ep, "save_mapping_sync", lambda _db, job_id, cols, product_line=None: state["saved"].append(product_line)
    )
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _stub_user()
    state["refresh_calls"] = refresh_calls
    return state


_COLS = [{"header": "id", "target": "technical_product_id"}]


def test_pm_mapping_save_accepts_sellable_line(pm_put) -> None:
    r = client.put("/api/v1/imports/product-master/jobs/1/mapping", json={"columns": _COLS, "product_line": " MB "})
    assert r.status_code == 200, r.text
    assert pm_put["saved"] == ["MB"]


def test_pm_mapping_save_rejects_unknown_line_after_one_refresh(pm_put) -> None:
    r = client.put("/api/v1/imports/product-master/jobs/1/mapping", json={"columns": _COLS, "product_line": "ZZ"})
    assert r.status_code == 400
    assert "Unknown product line" in r.json()["detail"]
    assert pm_put["saved"] == []
    assert pm_put["refresh_calls"] == [False, True]


def test_pm_mapping_save_without_line_uses_source_default(pm_put) -> None:
    r = client.put("/api/v1/imports/product-master/jobs/1/mapping", json={"columns": _COLS, "product_line": "  "})
    assert r.status_code == 200
    assert pm_put["saved"] == [None]
    assert pm_put["refresh_calls"] == []


def test_pm_mapping_save_other_grain_skips_product_line_check(pm_put) -> None:
    pm_put["grain"] = "feed"
    r = client.put("/api/v1/imports/product-master/jobs/1/mapping", json={"columns": _COLS, "product_line": "ZZ"})
    assert r.status_code == 200
    assert pm_put["saved"] == ["ZZ"]
    assert pm_put["refresh_calls"] == []


def test_pm_state_suggests_on_tenant_grain_and_reports_it(pm_put, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.v1.endpoints.imports_product_master as ep

    pm_put["grain"] = "feed"
    job = SimpleNamespace(
        id=1,
        tenant_id="default",
        template_slug="product_master",
        stage="pm_headers",
        status="draft",
        file_name="pm.xlsx",
        file_headers=["odd_col"],
        source=SimpleNamespace(id=1),
        inferred_schema=None,
        mapping_decisions=None,
        validation_passed=None,
        error_summary=None,
        staged_metadata={"duplicate_ean_flag": True, "duplicate_ean_count": 3},
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=job)
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    async def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    calls: list[dict] = []
    monkeypatch.setattr(ep, "reconcile_stale_pm_validate_sync", lambda _db, _job: False)
    monkeypatch.setattr(ep, "build_pm_import_progress", lambda _job, _sev: {})
    monkeypatch.setattr(
        ep,
        "suggest_mapping_decisions",
        lambda headers, source, inferred, product_line=None, grain=None: calls.append(
            {"product_line": product_line, "grain": grain}
        )
        or {},
    )
    r = client.get("/api/v1/imports/product-master/jobs/1/state?product_line=NB")
    assert r.status_code == 200, r.text
    body = r.json()
    assert calls == [{"product_line": "NB", "grain": "feed"}]
    assert body["column_grain"] == "feed"
    assert body["product_line"] == "NB"
    # D-0060: duplicate EAN is a FLAG on the job, never a block.
    assert body["duplicate_ean_flag"] is True
    assert body["duplicate_ean_count"] == 3


def test_pm_mapping_save_is_admin_only(pm_put) -> None:
    app.dependency_overrides[get_current_user] = _stub_user(Role.STEWARD)
    r = client.put("/api/v1/imports/product-master/jobs/1/mapping", json={"columns": _COLS, "product_line": "MB"})
    assert r.status_code == 403
    assert pm_put["saved"] == []

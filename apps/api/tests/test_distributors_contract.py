from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.ingestion.pipeline import _process_distributor_master
from app.main import app
from app.models.dimensions import DimDistributor
from app.models.ingestion import ImportRowResult


def _fake_dist_row(**overrides):
    base = {
        "id": 1,
        "distributor_code": "DIST-001",
        "distributor_name": "Summit Supply",
        "linked_sellout_rows": 12,
        "linked_inbound_rows": 7,
        "total_sellout_rows": 20,
        "total_inbound_rows": 10,
        "location_count": 2,
        "contact_count": 1,
        "latest_sellout_period_start": SimpleNamespace(isoformat=lambda: "2026-04-01"),
        "latest_inbound_eta_date": SimpleNamespace(isoformat=lambda: "2026-04-10"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_distributors_list_response_shape_and_query_contract():
    sess = MagicMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 2
    rows_res = MagicMock()
    rows_res.all.return_value = [
        _fake_dist_row(id=1, distributor_code="DIST-001", distributor_name="Summit Supply"),
        _fake_dist_row(
            id=2,
            distributor_code="DIST-002",
            distributor_name="North Hub",
            linked_sellout_rows=0,
            linked_inbound_rows=0,
            total_sellout_rows=0,
            total_inbound_rows=0,
            latest_sellout_period_start=None,
            latest_inbound_eta_date=None,
        ),
    ]
    sess.execute = AsyncMock(side_effect=[count_res, rows_res])

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            r = client.get(
                "/api/v1/distributors",
                params={
                    "page": 1,
                    "page_size": 25,
                    "q": "DIST",
                    "sort_by": "distributor_code",
                    "sort_dir": "asc",
                    "linkage_status": "partial",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 25
        assert body["total"] == 2
        assert body["sort_by"] == "distributor_code"
        assert body["sort_dir"] == "asc"
        assert len(body["items"]) == 2
        assert body["items"][0]["distributor_code"] == "DIST-001"
        assert body["items"][0]["distributor_name"] == "Summit Supply"
        assert body["items"][0]["linkage_status"] == "partial"
        assert body["items"][0]["location_count"] == 2
        assert body["items"][0]["contact_count"] == 1
        assert body["items"][1]["linkage_status"] == "no_fact_links"
    finally:
        app.dependency_overrides.clear()


def test_distributor_create_and_patch_contract_uses_phase1_field_names():
    row = SimpleNamespace(id=11, code="DIST-011", name="Old Name")
    existing = MagicMock()
    existing.scalars.return_value.first.return_value = None

    sess = MagicMock()
    sess.execute = AsyncMock(return_value=existing)
    sess.commit = AsyncMock()

    async def refresh_side_effect(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 11

    sess.refresh = AsyncMock(side_effect=refresh_side_effect)
    sess.get = AsyncMock(return_value=row)

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/v1/distributors",
                json={"distributor_code": "DIST-011", "distributor_name": "New Dist"},
            )
            assert create.status_code == 201
            body = create.json()
            assert body["distributor_code"] == "DIST-011"
            assert body["distributor_name"] == "New Dist"

            patch = client.patch("/api/v1/distributors/11", json={"distributor_name": "Renamed Dist"})
            assert patch.status_code == 200
            assert patch.json()["distributor_name"] == "Renamed Dist"
    finally:
        app.dependency_overrides.clear()


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _PipelineDB:
    def __init__(self):
        self._distributors = [SimpleNamespace(code="DIST-EXIST", name="Existing Dist")]
        self.added = []

    def scalars(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is DimDistributor:
            return _ScalarRows(self._distributors)
        return _ScalarRows([])

    def add(self, obj):
        self.added.append(obj)


def test_distributor_master_import_validate_and_apply_paths():
    mapping = {"Distributor Code": "distributor_code", "Distributor Name": "distributor_name"}
    df = pd.DataFrame([{"Distributor Code": "DIST-NEW", "Distributor Name": "New Distributor"}])

    validate_db = _PipelineDB()
    job_validate = SimpleNamespace(id=91, import_mode="validate", stage="validated")
    errs_validate = _process_distributor_master(validate_db, job_validate, df, mapping)
    assert errs_validate == 0
    validate_infos = [x for x in validate_db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "distributor_master_validated" for r in validate_infos)
    assert not any(isinstance(x, DimDistributor) for x in validate_db.added)

    apply_db = _PipelineDB()
    job_apply = SimpleNamespace(id=92, import_mode="apply", stage="validated")
    errs_apply = _process_distributor_master(apply_db, job_apply, df, mapping)
    assert errs_apply == 0
    apply_infos = [x for x in apply_db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "distributor_master_applied" for r in apply_infos)
    assert any(isinstance(x, DimDistributor) and x.code == "DIST-NEW" for x in apply_db.added)


def test_distributor_master_import_reports_row_level_diagnostics():
    mapping = {"Distributor Code": "distributor_code", "Distributor Name": "distributor_name"}
    df = pd.DataFrame(
        [
            {"Distributor Code": "", "Distributor Name": "Bad One"},
            {"Distributor Code": "DIST-1", "Distributor Name": ""},
            {"Distributor Code": "DIST-1", "Distributor Name": "Dup"},
        ]
    )
    db = _PipelineDB()
    job = SimpleNamespace(id=93, import_mode="validate", stage="validated")
    errs = _process_distributor_master(db, job, df, mapping)
    assert errs == 3
    rows = [x for x in db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "blank_distributor_code" and r.row_number == 1 for r in rows)
    assert any(r.code == "blank_distributor_name" and r.row_number == 2 for r in rows)
    assert any(r.code == "duplicate_distributor_code_in_file" and r.row_number == 3 for r in rows)


def test_distributor_location_and_contact_create_validation():
    distributor = SimpleNamespace(id=1, code="DIST-1", name="North Hub")
    location = SimpleNamespace(
        id=101,
        distributor_id=1,
        location_code="LOC-01",
        location_name="Main Branch",
        location_type="branch",
        country_code="US",
        address_summary=None,
        is_active=True,
        notes_summary=None,
    )
    contact = SimpleNamespace(
        id=201,
        distributor_id=1,
        contact_name="Alex Ops",
        contact_role="operations",
        email="ops@example.com",
        phone=None,
        is_primary=False,
        is_active=True,
        notes_summary=None,
    )
    sess = MagicMock()
    sess.get = AsyncMock(
        side_effect=lambda model, pk: (
            distributor
            if model.__name__ == "DimDistributor" and pk == 1
            else location
            if model.__name__ == "DistributorLocation" and pk == 101
            else contact
            if model.__name__ == "DistributorContact" and pk == 201
            else None
        )
    )
    sess.commit = AsyncMock()
    sess.refresh = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    exec_result.scalar_one.return_value = 0
    sess.execute = AsyncMock(return_value=exec_result)

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            bad_loc = client.post(
                "/api/v1/distributors/1/locations",
                json={"location_code": "LOC-1", "location_name": "Main", "location_type": "planet"},
            )
            assert bad_loc.status_code == 400

            ok_loc = client.post(
                "/api/v1/distributors/1/locations",
                json={"location_code": "LOC-1", "location_name": "Main", "location_type": "branch"},
            )
            assert ok_loc.status_code == 201

            bad_contact = client.post(
                "/api/v1/distributors/1/contacts",
                json={"contact_name": "Alex", "contact_role": "wizard"},
            )
            assert bad_contact.status_code == 400

            ok_contact = client.post(
                "/api/v1/distributors/1/contacts",
                json={"contact_name": "Alex", "contact_role": "operations"},
            )
            assert ok_contact.status_code == 201
    finally:
        app.dependency_overrides.clear()

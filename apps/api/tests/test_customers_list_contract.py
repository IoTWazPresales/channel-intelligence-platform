from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.ingestion.pipeline import _process_customer_master
from app.main import app
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimRegion
from app.models.ingestion import ImportRowResult


def _fake_customer(**overrides):
    base = {
        "id": 1,
        "code": "CUST-001",
        "name": "Metro Market",
        "customer_status": "active",
        "no_code_disposition": None,
        "is_key_account": False,
        "created_at": None,
        "updated_at": None,
        "partner_tier": "strategic",
        "account_owner_internal": "owner@cip.local",
        "notes_summary": "Priority partner",
        "region_id": 11,
        "channel_id": 22,
        "preferred_distributor_id": 33,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_customers_list_response_shape_and_pagination_contract():
    sess = MagicMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 2
    rows_res = MagicMock()
    rows_res.all.return_value = [
        (_fake_customer(id=1, code="A-CUST"), "NA-W", "RET", "DIST-01", "Summit Supply", 2, 1, 3, None),
        (_fake_customer(id=2, code="B-CUST", partner_tier=None), None, None, None, None, 0, 0, 0, None),
    ]
    sess.execute = AsyncMock(side_effect=[count_res, rows_res])

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            r = client.get(
                "/api/v1/customers",
                params={
                    "page": 1,
                    "page_size": 25,
                    "sort_by": "code",
                    "sort_dir": "asc",
                    "q": "CUST",
                    "customer_status": "active",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 25
        assert body["total"] == 2
        assert body["sort_by"] == "code"
        assert body["sort_dir"] == "asc"
        assert len(body["items"]) == 2
        assert body["items"][0]["customer_code"] == "A-CUST"
        assert body["items"][0]["customer_status"] == "active"
        assert body["items"][0]["partner_tier"] == "strategic"
        assert body["items"][0]["region_code"] == "NA-W"
        assert body["items"][0]["channel_code"] == "RET"
        assert body["items"][0]["preferred_distributor_code"] == "DIST-01"
        assert body["items"][0]["preferred_distributor_name"] == "Summit Supply"
        assert body["items"][0]["location_count"] == 2
        assert body["items"][0]["contact_count"] == 1
        assert body["items"][1]["preferred_distributor_code"] is None
    finally:
        app.dependency_overrides.clear()


def test_customer_patch_validates_controlled_vocab_fields():
    existing = _fake_customer()
    region = SimpleNamespace(id=11, code="NA-W", name="North America West")
    channel = SimpleNamespace(id=22, code="RET", name="Retail")
    distributor = SimpleNamespace(id=33, code="DIST-01", name="Summit Supply")

    sess = MagicMock()
    sess.get = AsyncMock(
        side_effect=lambda model, pk: (
            existing
            if pk == 1
            else region
            if pk == 11
            else channel
            if pk == 22
            else distributor
            if pk == 33
            else None
        )
    )
    sess.commit = AsyncMock()
    sess.refresh = AsyncMock()

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            bad = client.patch("/api/v1/customers/1", json={"customer_status": "weird"})
            assert bad.status_code == 400
            assert "customer_status" in bad.json()["detail"]

            bad_tier = client.patch("/api/v1/customers/1", json={"partner_tier": "goldish"})
            assert bad_tier.status_code == 400
            assert "partner_tier" in bad_tier.json()["detail"]

            ok = client.patch(
                "/api/v1/customers/1",
                json={
                    "customer_status": "blocked",
                    "partner_tier": "tier_2",
                    "account_owner_internal": "sales.rep",
                    "preferred_distributor_id": 33,
                },
            )
            assert ok.status_code == 200
            body = ok.json()
            assert body["customer_status"] == "blocked"
            assert body["partner_tier"] == "tier_2"
            assert body["account_owner_internal"] == "sales.rep"
    finally:
        app.dependency_overrides.clear()


def test_customer_create_generates_temporary_code_when_code_blank():
    sess = MagicMock()
    sess.get = AsyncMock(
        side_effect=lambda _model, pk: (
            SimpleNamespace(id=11, code="NA-W", name="North America West")
            if pk == 11
            else SimpleNamespace(id=22, code="RET", name="Retail")
            if pk == 22
            else None
        )
    )
    exists_res = MagicMock()
    exists_res.scalar_one_or_none.return_value = None
    sess.execute = AsyncMock(return_value=exists_res)
    sess.commit = AsyncMock()

    async def refresh_side_effect(row):
        if getattr(row, "id", None) is None:
            row.id = 99

    sess.refresh = AsyncMock(side_effect=refresh_side_effect)

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/v1/customers",
                json={
                    "customer_code": "",
                    "customer_name": "  Fresh Mart  ",
                    "customer_status": "active",
                    "region_id": 11,
                    "channel_id": 22,
                },
            )
        assert r.status_code == 201
        body = r.json()
        assert body["customer_code"].startswith("TMP-CUST-")
        assert body["customer_name"] == "Fresh Mart"
        assert body["region_code"] == "NA-W"
        assert body["channel_code"] == "RET"
    finally:
        app.dependency_overrides.clear()


def test_customer_create_rejects_invalid_region_lookup():
    sess = MagicMock()
    sess.get = AsyncMock(return_value=None)

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            bad_lookup = client.post(
                "/api/v1/customers",
                json={
                    "customer_code": "CUST-NEW",
                    "customer_name": "Fresh Mart",
                    "customer_status": "active",
                    "region_id": 999,
                    "channel_id": 22,
                },
            )
            assert bad_lookup.status_code == 400
            assert "region_id" in bad_lookup.json()["detail"]
    finally:
        app.dependency_overrides.clear()


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _PipelineDB:
    def __init__(self):
        self._regions = [SimpleNamespace(id=11, code="NA-W")]
        self._channels = [SimpleNamespace(id=22, code="RET")]
        self._distributors = [SimpleNamespace(id=33, code="DIST-01")]
        self._customers = [SimpleNamespace(code="CUST-EXIST", name="Existing")]
        self.added = []

    def scalars(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is DimRegion:
            return _ScalarRows(self._regions)
        if entity is DimChannel:
            return _ScalarRows(self._channels)
        if entity is DimDistributor:
            return _ScalarRows(self._distributors)
        if entity is DimCustomer:
            return _ScalarRows(self._customers)
        return _ScalarRows([])

    def add(self, obj):
        self.added.append(obj)


def test_customer_master_import_validate_and_apply_paths():
    mapping = {
        "Customer Code": "customer_code",
        "Customer Name": "customer_name",
        "Region": "region_code",
        "Channel": "channel_code",
        "Status": "customer_status",
    }
    df = pd.DataFrame(
        [
            {
                "Customer Code": "CUST-NEW",
                "Customer Name": "New Customer",
                "Region": "NA-W",
                "Channel": "RET",
                "Status": "active",
            }
        ]
    )

    validate_db = _PipelineDB()
    job_validate = SimpleNamespace(id=91, import_mode="validate", stage="validated")
    errs_validate = _process_customer_master(validate_db, job_validate, df, mapping)
    assert errs_validate == 0
    validate_infos = [x for x in validate_db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "customer_master_validated" for r in validate_infos)
    assert not any(isinstance(x, DimCustomer) for x in validate_db.added)

    apply_db = _PipelineDB()
    job_apply = SimpleNamespace(id=92, import_mode="apply", stage="validated")
    errs_apply = _process_customer_master(apply_db, job_apply, df, mapping)
    assert errs_apply == 0
    apply_infos = [x for x in apply_db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "customer_master_applied" for r in apply_infos)
    assert any(isinstance(x, DimCustomer) and x.code == "CUST-NEW" for x in apply_db.added)


def test_customer_master_import_reports_row_level_diagnostics():
    mapping = {"Customer Code": "customer_code", "Customer Name": "customer_name", "Region": "region_code"}
    df = pd.DataFrame([{"Customer Code": "CUST-1", "Customer Name": "Name", "Region": "UNKNOWN"}])
    db = _PipelineDB()
    job = SimpleNamespace(id=93, import_mode="validate", stage="validated")
    errs = _process_customer_master(db, job, df, mapping)
    assert errs == 1
    rows = [x for x in db.added if isinstance(x, ImportRowResult)]
    assert any(r.code == "unknown_region_code" and r.row_number == 1 for r in rows)


def test_customer_location_and_contact_create_validation():
    customer = _fake_customer(id=1)
    region = SimpleNamespace(id=11, code="NA-W")
    sess = MagicMock()
    sess.get = AsyncMock(
        side_effect=lambda model, pk: (
            customer
            if model.__name__ == "DimCustomer" and pk == 1
            else region
            if model.__name__ == "DimRegion" and pk == 11
            else None
        )
    )
    sess.commit = AsyncMock()

    async def refresh_side_effect(row):
        if getattr(row, "id", None) is None:
            row.id = 501

    sess.refresh = AsyncMock(side_effect=refresh_side_effect)

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            bad_location = client.post(
                "/api/v1/customers/1/locations",
                json={
                    "location_code": "LOC-1",
                    "location_name": "Main",
                    "location_type": "invalid",
                    "region_id": 11,
                },
            )
            assert bad_location.status_code == 400

            ok_location = client.post(
                "/api/v1/customers/1/locations",
                json={
                    "location_code": "LOC-1",
                    "location_name": "Main",
                    "location_type": "store",
                    "region_id": 11,
                },
            )
            assert ok_location.status_code == 201

            bad_contact = client.post(
                "/api/v1/customers/1/contacts",
                json={"contact_name": "Alex", "contact_role": "invalid"},
            )
            assert bad_contact.status_code == 400
    finally:
        app.dependency_overrides.clear()

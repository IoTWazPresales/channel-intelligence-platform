"""N-0088: a stored mapping profile is written on export and read back by the existing parser.

Does not rebuild the fixed 32-column workbook or the historical import pipeline.
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.cpor.historical_import.parser import parse_historical_workbook
from app.services.cpor.profile_layout_export import (
    build_case_profile_workbook,
    load_mapping_profile,
    profile_as_dict,
    render_profile_workbook,
)


def _sample_profile() -> dict:
    return {
        "profile_code": "tenant_plan_layout_v1",
        "display_name": "Tenant plan layout",
        "header_row_index": 1,
        "sheet_roles_json": {"Plan lines": "reseller"},
        "column_order": [
            "case_code",
            "customer_token",
            "sales_model_token",
            "promotion_type",
            "window_start",
            "estimate_qty",
            "srp",
        ],
        "column_map_json": {
            "case_code": ["Plan ref"],
            "customer_token": ["Account"],
            "sales_model_token": ["Model"],
            "promotion_type": ["Mechanic"],
            "window_start": ["From"],
            "estimate_qty": ["Units"],
            "srp": ["Shelf"],
        },
    }


def test_profile_workbook_round_trips_through_the_existing_parser():
    profile = _sample_profile()
    row = {
        "case_code": "C26P00077",
        "customer_token": "North account",
        "sales_model_token": "MODEL-1",
        "promotion_type": "Sell out PP",
        "window_start": "2026-10-01",
        "estimate_qty": 23,
        "srp": 199.5,
    }
    data, meta = render_profile_workbook(profile, [row])
    assert meta["layout"] == "mapping_profile"
    assert meta["headers"] == ["Plan ref", "Account", "Model", "Mechanic", "From", "Units", "Shelf"]
    parsed = parse_historical_workbook(data, profile=profile)
    assert parsed["blocking_errors"] == []
    assert len(parsed["rows"]) == 1
    got = parsed["rows"][0]
    assert got["case_code"] == "C26P00077"
    assert got["customer_token"] == "North account"
    assert got["sales_model_token"] == "MODEL-1"
    assert got["estimate_qty"] == 23
    assert got["srp"] == 199.5
    assert str(got["window_start"]) == "2026-10-01"


def test_empty_map_is_refused():
    try:
        render_profile_workbook({"column_map_json": {}, "sheet_roles_json": {"Plan": "reseller"}}, [])
    except ValueError as exc:
        assert str(exc) == "empty_column_map"
    else:
        raise AssertionError("empty column map was accepted")


def test_stored_profile_export_query_runs_on_cip_test():
    """Read the stored profile, if one exists, and render one synthetic row. No write."""
    with SessionLocal() as session:
        name = session.execute(text("SELECT current_database()")).scalar()
        print("SELECT current_database()", name)
        assert name == "cip_test"
        stored = load_mapping_profile(session)
        if stored is None:
            session.rollback()
            return
        profile = profile_as_dict(stored)
        profile_code = stored.profile_code
        if not profile.get("column_order"):
            session.rollback()
            return
        data, meta = render_profile_workbook(
            profile,
            [
                {
                    "case_code": "CIP-QTY-EXPORT",
                    "customer_token": "Sample account",
                    "sales_model_token": "MODEL-1",
                    "estimate_qty": 5,
                    "promotion_type": "Sell out PP",
                    "window_start": "2026-10-01",
                    "srp": 10,
                }
            ],
        )
        session.rollback()
    assert data[:2] == b"PK"
    assert meta["layout"] == "mapping_profile"
    assert meta["profile_code"] == profile_code
    parsed = parse_historical_workbook(data, profile=profile)
    assert any(row["case_code"] == "CIP-QTY-EXPORT" for row in parsed["rows"])


def test_case_workbook_builder_is_not_this_module():
    """The fixed workbook function stays the other module. This one does not import it."""
    import app.services.cpor.profile_layout_export as mod

    assert not hasattr(mod, "build_cpor_case_workbook_bytes")
    assert build_case_profile_workbook is mod.build_case_profile_workbook


def test_distributor_case_uses_the_distributor_sheet():
    profile = _sample_profile()
    profile["sheet_roles_json"] = {
        "Reseller Sell out": "reseller",
        "Disti Sell out": "disti",
    }
    profile["channel"] = "distributor"
    _data, meta = render_profile_workbook(profile, [{"case_code": "C1", "estimate_qty": 2, "srp": 9}])
    assert meta["sheet"] == "Disti Sell out"
    assert meta["role"] == "disti"


def test_column_order_list_survives_postgres_jsonb_load():
    """JSONB object keys are not workbook order. The stored list is."""
    import uuid

    from app.models.cpor_historical import CporHistoricalMappingProfile

    order = ["srp", "case_code", "estimate_qty"]
    column_map = {
        "estimate_qty": ["Units"],
        "case_code": ["Plan ref"],
        "srp": ["Shelf"],
        "column_order": list(order),
    }
    with SessionLocal() as session:
        name = session.execute(text("SELECT current_database()")).scalar()
        print("SELECT current_database()", name)
        assert name == "cip_test"
        row = CporHistoricalMappingProfile(
            profile_code=f"w1c-order-{uuid.uuid4().hex[:12]}",
            display_name="Order probe",
            header_row_index=0,
            sheet_roles_json={"Reseller Sell out": "reseller", "Disti Sell out": "disti"},
            column_map_json=column_map,
            value_maps_json={},
            is_default=False,
        )
        session.add(row)
        session.flush()
        session.expire(row)
        loaded = profile_as_dict(row)
        session.rollback()
    assert loaded["column_order"] == order
    _data, meta = render_profile_workbook(loaded, [{"case_code": "C1", "estimate_qty": 2, "srp": 9}])
    assert meta["headers"] == ["Shelf", "Plan ref", "Units"]
    assert meta["headers"] != ["Plan ref", "Units", "Shelf"]

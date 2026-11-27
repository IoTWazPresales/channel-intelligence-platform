"""Database-free regressions for PR #92 quantity and workbook review findings."""

from contextlib import closing
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock

from openpyxl import load_workbook
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.cpor_historical import CporHistoricalMappingProfile
from app.services.cpor.historical_import.profile_defaults import (
    asus_default_profile_dict as default_profile_dict,
)
import app.services.cpor.profile_layout_export as exporter
import app.services.cpor.promo_plan_builder as quantities
import app.services.cpor.recompute as recompute


@pytest.fixture(autouse=True)
def refuse_database_connections():
    def refuse(*args, **kwargs):
        pytest.fail("These unit tests must never connect to a database")

    event.listen(Engine, "do_connect", refuse)
    yield
    event.remove(Engine, "do_connect", refuse)


@pytest.mark.parametrize("channel,role", [("reseller", "reseller"), ("distributor", "disti")])
def test_seeded_default_profile_exports_without_stored_column_order(monkeypatch, channel, role):
    seeded = default_profile_dict()
    # Simulate a stored JSONB map, whose key order differs from the seed's.
    stored_map = json.loads(json.dumps(seeded["column_map_json"], sort_keys=True))
    assert "column_order" not in stored_map
    stored = CporHistoricalMappingProfile(**{**seeded, "column_map_json": stored_map})
    session = Mock(spec=Session)
    session.scalar.return_value = stored
    session.get.return_value = SimpleNamespace(channel=channel)
    row = {"case_code": "CASE-1", "estimate_qty": 5, "srp": 12.5}
    monkeypatch.setattr(exporter, "canonical_rows_for_case", lambda *args: [row])

    data, meta = exporter.build_case_profile_workbook(session, 1)

    assert meta["role"] == role
    assert meta["line_count"] == 1
    assert meta["headers"][0] == stored_map["case_code"][0]
    # Generic fallback is deterministic; it does not depend on JSONB key order.
    assert meta["headers"] == [
        header for _, header in exporter.layout_columns(seeded["column_map_json"])
    ]
    with closing(load_workbook(BytesIO(data))) as wb:
        ws = wb[meta["sheet"]]
        values = dict(zip(meta["headers"], next(ws.iter_rows(min_row=3, max_row=3, values_only=True))))
        assert values[stored_map["case_code"][0]] == "CASE-1"
        assert values[stored_map["estimate_qty"][0]] == 5
        assert values[stored_map["srp"][0]] == 12.5


@pytest.mark.parametrize("text", ["=1+1", "+1+1", "-1+1", "@SUM(A1)"])
def test_profile_export_stores_formula_like_headers_and_values_as_literal_text(text):
    profile = {
        "header_row_index": 0,
        "sheet_roles_json": {"Plan": "reseller"},
        "column_order": ["case_code", "remark", "estimate_qty", "srp"],
        "column_map_json": {
            "case_code": ["Reference"],
            "remark": [text],
            "estimate_qty": ["Units"],
            "srp": ["Price"],
        },
    }
    data, _ = exporter.render_profile_workbook(
        profile, [{"case_code": text, "remark": text, "estimate_qty": -5, "srp": 12.5}]
    )

    with closing(load_workbook(BytesIO(data), data_only=False)) as wb:
        ws = wb["Plan"]
        for coordinate in ("B1", "A2", "B2"):
            assert ws[coordinate].value == text
            assert ws[coordinate].data_type == "s"
        assert ws["C2"].value == -5 and ws["C2"].data_type == "n"
        assert ws["D2"].value == 12.5 and ws["D2"].data_type == "n"
        assert all(cell.data_type != "f" for row in ws for cell in row)


def test_explicit_profile_order_still_takes_priority_and_empty_maps_fail():
    columns = {"case_code": ["Reference"], "estimate_qty": ["Units"]}
    assert exporter.layout_columns(columns, ["estimate_qty", "case_code"]) == [
        ("estimate_qty", "Units"), ("case_code", "Reference")
    ]
    assert exporter.layout_columns({**columns, "column_order": ["estimate_qty", "case_code"]}) == [
        ("estimate_qty", "Units"), ("case_code", "Reference")
    ]
    with pytest.raises(ValueError, match="^empty_column_map$"):
        exporter.render_profile_workbook({"column_map_json": {}}, [])


@pytest.mark.parametrize("other_distributor,other_quarter", [(1, "26Q1"), (2, "26Q1"), (1, "26Q2")])
def test_sku_suggestion_targets_one_live_layer_in_preview_and_apply(
    monkeypatch, other_distributor, other_quarter
):
    case = CporCase(currency_code="ZAR", id=1, customer_id=1)

    def line(ident, product=1, qty=0, remark=None, distributor=1, quarter="26Q1"):
        return CporCaseLine(
            id=ident, case_id=case.id, product_id=product, estimate_qty=qty,
            remark=remark, distributor_id=distributor, pod_quarter=quarter, srp=100,
        )

    retired = line(10, remark="[split into layers]")
    target = line(11, qty=4)
    other_layer = line(12, qty=7, distributor=other_distributor, quarter=other_quarter)
    voided = line(13, remark="[voided]")
    unresolved = line(14, product=None)
    other_product = line(15, product=2, qty=3)
    lines = [retired, target, other_layer, voided, unresolved, other_product]
    session = Mock(spec=Session)
    session.get.return_value = case
    session.scalars.return_value.all.return_value = lines

    def draft(_session, **kwargs):
        return {"lines": [
            {"seed_line_id": spec["seed_line_id"], "product_id": spec["product_id"],
             "suggested_estimate_qty": 40, "quantity_evidence": {"blocks": False}, "flags": []}
            for spec in kwargs["line_specs"]
        ]}

    compose = Mock(side_effect=draft)
    recalculate = Mock()
    monkeypatch.setattr(quantities, "build_promo_plan_draft", compose)
    monkeypatch.setattr(recompute, "recompute_case_line", recalculate)

    preview = quantities.preview_cip_quantities(session, case_id=case.id)
    assert [row["line_id"] for row in preview["lines"]] == [target.id, other_product.id]
    assert [spec["seed_line_id"] for spec in compose.call_args.kwargs["line_specs"]] == [11, 15]
    assert [float(item.estimate_qty) for item in lines] == [0, 4, 7, 0, 0, 3]

    for _ in range(2):
        result = quantities.apply_cip_quantities(session, case)
        assert [row["line_id"] for row in result["lines"]] == [11, 15]
        assert target.estimate_qty == 40
        assert other_layer.estimate_qty == 7
        assert other_product.estimate_qty == 40
        assert retired.estimate_qty == voided.estimate_qty == unresolved.estimate_qty == 0
        assert result["blocks"] is False
    assert [call.args[1].id for call in recalculate.call_args_list] == [11, 15, 11, 15]
    session.commit.assert_not_called()

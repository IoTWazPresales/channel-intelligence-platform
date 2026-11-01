"""On the water: voyage columns read from a shipment row (no database)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.models.shipment_water import WATER_DATE_FIELDS, WATER_FIELDS, WATER_TEXT_FIELDS, WATER_TEXT_WIDTH
from app.services.imports.shipment_evidence_import import _extract_common, _parse_date
from app.services.imports.shipment_evidence_line_identity import observation_payload_hash
from app.services.imports.shipment_field_mapping import (
    SHIPMENT_CANONICAL_TARGETS,
    SHIPMENT_FIELD_TARGET_DESCRIPTIONS,
    build_initial_shipment_field_mapping,
)
from app.services.imports.shipment_voyage import (
    DEFAULT_SHIPPING_METHOD_PATTERN,
    compile_shipping_method_pattern,
    split_shipping_method,
    voyage_fields,
)

# Real values from the ACZA Shipped_Unshipped reports (counted on cip, 110 832 lines).
ACZA_SHIPPING_METHODS = [
    ("COSCOckg-WWP-Truck/Sea--", "COSCO", "ckg"),
    ("KGILckg-WWP-Truck/Air--", "KGIL", "ckg"),
    ("WWPc-Sea--", "WWP", "c"),
    ("COSCOszx-WWP-Sea--", "COSCO", "szx"),
    ("KGILsha-WWP-Sea--", "KGIL", "sha"),
    ("PREMIEREnl-Sea--", "PREMIERE", "nl"),
    ("PFEDEXHKc-GS-Express--", "PFEDEXHK", "c"),
    # A forwarder written in Chinese, and values with no hub at all.
    ("凌凱ckg-Air--", "凌凱", "ckg"),
    ("凌凱y-Sea--", "凌凱", "y"),
    ("PDHL-GS-Express--", "PDHL", None),
    ("WWP-Air--", "WWP", None),
    ("CLIENT-Sea--", "CLIENT", None),
]

ACZA_HEADERS = [
    "Operating Unit",
    "On-Board Date",
    "ETA Date(Est Port Arrival)",
    "ATA Date(Actual Port Arrival)",
    "Shipping Method",
    "Ship Way",
    "Deliver Port",
    "Container Number",
    "Currency",
]


@pytest.mark.parametrize(("value", "forwarder", "hub"), ACZA_SHIPPING_METHODS)
def test_default_pattern_reads_forwarder_and_hub(value, forwarder, hub):
    assert split_shipping_method(value) == (forwarder, hub)


def test_blank_or_unmatched_shipping_method_gives_nothing():
    assert split_shipping_method(None) == (None, None)
    assert split_shipping_method("  ") == (None, None)
    assert split_shipping_method("123-Sea--") == (None, None)


def test_a_tenant_pattern_replaces_the_default_and_must_name_the_forwarder():
    custom = compile_shipping_method_pattern(r"^(?P<forwarder>[A-Z]+)(?P<hub>[a-z]{2})")  # two-letter hubs only
    assert split_shipping_method("COSCOckg-WWP", custom) == ("COSCO", "ck")
    assert split_shipping_method("COSCOckg-WWP") == ("COSCO", "ckg")  # the default is untouched
    with pytest.raises(ValueError, match="forwarder"):
        compile_shipping_method_pattern(r"^(?P<hub>[a-z]+)")
    with pytest.raises(ValueError, match="valid pattern"):
        compile_shipping_method_pattern("(")
    assert compile_shipping_method_pattern("").pattern == DEFAULT_SHIPPING_METHOD_PATTERN


def test_voyage_fields_parse_dates_trim_text_and_read_forwarder_from_the_method():
    out = voyage_fields(
        {
            "on_board_date": "2026-09-02T00:00:00",
            "port_eta_date": "2026-10-20T00:00:00",
            "port_ata_date": None,
            "shipping_method": "  COSCOckg-WWP-Truck/Sea--  ",
            "ship_way": "SEA",
            "deliver_port": "ZADUR",
            "container_no": float("nan"),
            "vessel_name": "x" * 500,
        },
        parse_date=_parse_date,
    )
    assert set(out) == set(WATER_FIELDS)
    assert out["on_board_date"] == date(2026, 9, 2)
    assert out["port_eta_date"] == date(2026, 10, 20)
    assert out["port_ata_date"] is None
    assert (out["forwarder_code"], out["origin_hub"]) == ("COSCO", "ckg")
    assert out["shipping_method"] == "COSCOckg-WWP-Truck/Sea--"
    assert out["container_no"] is None
    assert len(out["vessel_name"]) == WATER_TEXT_WIDTH["vessel_name"]


def test_an_explicit_forwarder_or_hub_wins_and_ship_way_falls_back_to_the_older_shipway():
    out = voyage_fields(
        {"shipping_method": "COSCOckg-WWP--", "forwarder_code": "ACME", "origin_hub": "dur", "shipway": "TRUCK/SEA"},
        parse_date=_parse_date,
    )
    assert (out["forwarder_code"], out["origin_hub"]) == ("ACME", "dur")
    assert out["ship_way"] == "TRUCK/SEA"


def test_every_voyage_field_is_a_mapping_target_with_help_text():
    for name in WATER_FIELDS:
        assert name in SHIPMENT_CANONICAL_TARGETS
        assert SHIPMENT_FIELD_TARGET_DESCRIPTIONS.get(name), name


def test_acza_headers_map_to_the_voyage_fields_and_container_number_does_not():
    mapping = build_initial_shipment_field_mapping(ACZA_HEADERS, None)
    assert mapping["On-Board Date"] == "on_board_date"
    assert mapping["ETA Date(Est Port Arrival)"] == "port_eta_date"
    assert mapping["ATA Date(Actual Port Arrival)"] == "port_ata_date"
    assert mapping["Shipping Method"] == "shipping_method"
    assert mapping["Ship Way"] == "ship_way"
    assert mapping["Deliver Port"] == "deliver_port"
    assert mapping["Currency"] == "currency_code"
    # ACZA's 5-digit internal number is not an ISO 6346 container number.
    assert "Container Number" not in mapping
    assert "container_no" not in mapping.values()


def test_extract_common_carries_the_voyage_fields_through_the_mapping():
    row = pd.Series(
        {
            "On-Board Date": "2026-09-02T00:00:00",
            "ETA Date(Est Port Arrival)": "2026-10-20T00:00:00",
            "ATA Date(Actual Port Arrival)": "2026-10-19T00:00:00",
            "Shipping Method": "KGILsha-WWP-Sea--",
            "Ship Way": "SEA",
            "Deliver Port": "ZADUR",
            "Container Number": 71234,
        }
    )
    ex = _extract_common(row, {v: k for k, v in build_initial_shipment_field_mapping(list(row.index), None).items()})
    assert ex["on_board_date"] == date(2026, 9, 2)
    assert ex["port_eta_date"] == date(2026, 10, 20)
    assert ex["port_ata_date"] == date(2026, 10, 19)
    assert (ex["forwarder_code"], ex["origin_hub"], ex["ship_way"], ex["deliver_port"]) == ("KGIL", "sha", "SEA", "ZADUR")
    assert ex["container_no"] is None


def test_the_voyage_columns_do_not_change_an_observation_hash():
    base = {"source_sheet": "Shipped", "source_row_number": 4, "report_type": "acza_shipped", "line_state": "shipped"}
    assert observation_payload_hash(base) == observation_payload_hash({**base, "port_eta_date": date(2026, 10, 20), "ship_way": "SEA"})


def test_the_migration_and_the_model_agree_on_the_columns_and_widths():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261101_0049_on_the_water.py"
    spec = importlib.util.spec_from_file_location("mig_0049", path)
    mig = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mig)
    assert tuple(mig.DATE_COLUMNS) == WATER_DATE_FIELDS
    assert dict(mig.TEXT_COLUMNS) == WATER_TEXT_WIDTH
    assert tuple(mig.TEXT_COLUMNS) == WATER_TEXT_FIELDS
    assert mig.down_revision == "20261023_0048"

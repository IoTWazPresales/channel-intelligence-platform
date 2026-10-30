"""Saved shipment mapping and remembered sheets skip the confirm steps."""

from types import SimpleNamespace

from app.services.imports.shipment_field_mapping import (
    headers_match_saved_shipment_mapping,
    remembered_sheet_names,
)


def test_headers_match_when_every_header_has_the_saved_target():
    source = SimpleNamespace(
        column_mapping_memory={
            "by_header_norm": {
                "bill_to": {"target": "bill_to_raw"},
                "item": {"target": "item_code"},
            }
        }
    )
    headers = ["Bill To", "Item"]
    mapping = {"Bill To": "bill_to_raw", "Item": "item_code"}
    assert headers_match_saved_shipment_mapping(headers, source, mapping) is True


def test_headers_do_not_match_when_a_header_was_never_saved():
    source = SimpleNamespace(
        column_mapping_memory={"by_header_norm": {"item": {"target": "item_code"}}}
    )
    headers = ["Item", "Qty"]
    mapping = {"Item": "item_code", "Qty": "quantity"}
    assert headers_match_saved_shipment_mapping(headers, source, mapping) is False


def test_unmapped_extra_header_still_matches_the_saved_mapping():
    source = SimpleNamespace(
        column_mapping_memory={
            "by_header_norm": {
                "bill_to": {"target": "bill_to_raw"},
                "item": {"target": "item_code"},
            }
        }
    )
    headers = ["Bill To", "Item", "Internal note"]
    mapping = {"Bill To": "bill_to_raw", "Item": "item_code"}
    assert headers_match_saved_shipment_mapping(headers, source, mapping) is True


def test_remembered_sheet_names_round_trip_from_source_memory():
    source = SimpleNamespace(
        column_mapping_memory={"selected_sheet_names": ["Unship", "Shipped", "BOM not ready"]}
    )
    assert remembered_sheet_names(source) == ["Unship", "Shipped", "BOM not ready"]
    assert remembered_sheet_names(SimpleNamespace(column_mapping_memory={})) == []

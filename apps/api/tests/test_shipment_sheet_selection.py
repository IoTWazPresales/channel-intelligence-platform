from app.services.imports.shipment_evidence_import import default_selected_sheets
from app.services.imports.shipment_field_mapping import initial_sheet_selection
from app.services.supply_overview import _OPEN_TWIN_REMAINDER
from types import SimpleNamespace


def test_default_sheets_prefer_shipped_and_unship_not_bom():
    """D-0025: BOM Not Ready is listed for the picker but starts unticked."""
    names = ["Cover", "Shipped", "BOM Not Ready", "Unship"]
    chosen = default_selected_sheets(names)
    assert chosen == ["Shipped", "Unship"]
    assert "BOM Not Ready" not in chosen
    # Still present in the workbook so the operator can tick it.
    assert "BOM Not Ready" in names


def test_default_sheets_keep_a_workbook_with_no_preferred_names():
    chosen = default_selected_sheets(["Orders"])
    assert chosen == ["Orders"]


def test_default_sheets_exclude_bom_when_no_preferred_names():
    chosen = default_selected_sheets(["Cover", "BOM Not Ready", "Notes"])
    assert chosen == ["Cover", "Notes"]
    assert "BOM Not Ready" not in chosen


def test_default_sheets_keep_bom_only_workbook():
    # One-tab / only-excluded workbook must not drop every sheet.
    chosen = default_selected_sheets(["BOM Not Ready"])
    assert chosen == ["BOM Not Ready"]


def test_remembered_selection_can_still_include_bom():
    source = SimpleNamespace(
        column_mapping_memory={
            "selected_sheet_names": ["Shipped", "Unship", "BOM Not Ready"],
            "seen_sheet_names": ["Cover", "Shipped", "BOM Not Ready", "Unship"],
        }
    )
    names = ["Cover", "Shipped", "BOM Not Ready", "Unship"]
    defaults = default_selected_sheets(names)
    chosen, confirmed, changes = initial_sheet_selection(source, names, defaults)
    assert chosen == ["Shipped", "BOM Not Ready", "Unship"]
    assert confirmed is True
    assert changes["new"] == []


def test_open_count_uses_strict_shipped_pair():
    sql = _OPEN_TWIN_REMAINDER.lower()
    assert "operating_unit" in sql
    assert "order_no" in sql
    assert "item_code" in sql
    assert "line_state" in sql
    assert "shipped" in sql

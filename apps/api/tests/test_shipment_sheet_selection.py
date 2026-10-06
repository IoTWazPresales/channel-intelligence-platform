from app.services.imports.shipment_evidence_import import default_selected_sheets
from app.services.supply_overview import _OPEN_HAS_SHIPPED_TWIN


def test_default_sheets_prefer_shipped_and_unship():
    chosen = default_selected_sheets(["Cover", "Shipped", "BOM Not Ready", "Unship"])
    assert chosen == ["Shipped", "Unship"]


def test_default_sheets_keep_a_workbook_with_no_preferred_names():
    chosen = default_selected_sheets(["Orders"])
    assert chosen == ["Orders"]


def test_open_count_uses_strict_shipped_pair():
    sql = _OPEN_HAS_SHIPPED_TWIN.lower()
    assert "operating_unit" in sql
    assert "order_no" in sql
    assert "item_code" in sql
    assert "line_state" in sql
    assert "shipped" in sql

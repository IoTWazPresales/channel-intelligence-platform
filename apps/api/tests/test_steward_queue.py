"""Steward failure-queue registry: grouping is data-driven; hrefs are config."""

from app.services.imports.steward_queue import (
    STEWARD_QUEUE_RESOLUTION,
    decorate_group,
    decorate_item,
    resolution_href,
    resolution_label,
)


def test_known_dsi_and_cst_route_to_import_job_workspace() -> None:
    assert resolution_href("product_identifier", 43) == "/admin/imports?job=43"
    assert resolution_href("customer_dealer_token", 43) == "/admin/imports?job=43"
    assert resolution_href("distributor_token", 43) == "/admin/imports?job=43"
    assert resolution_href("cst_product_token", 12) == "/admin/imports?job=12"
    assert resolution_href("cst_location_token", 12) == "/admin/imports?job=12"


def test_known_shipment_types_route_to_shipment_evidence() -> None:
    assert resolution_href("shipment_distributor", 9) == "/admin/shipment-evidence?importJobId=9"
    assert resolution_href("shipment_customer_token", 9) == "/admin/shipment-evidence?importJobId=9"


def test_unknown_entity_type_is_uncovered_not_invented() -> None:
    assert "future_importer_token" not in STEWARD_QUEUE_RESOLUTION
    assert resolution_href("future_importer_token", 1) is None
    group = decorate_group("future_importer_token", 4, 2, 10)
    assert group["entity_type"] == "future_importer_token"
    assert group["label"] == "future_importer_token"
    assert group["covered"] is False
    assert group["candidate_count"] == 4


def test_decorate_item_keeps_job_as_provenance() -> None:
    item = decorate_item(
        {
            "id": 7,
            "entity_type": "product_identifier",
            "normalized_key": "sku-1",
            "row_count": 3,
            "total_units": 10,
            "status": "needs_review",
            "import_job_id": 88,
            "template_slug": "distributor_inventory",
            "file_name": "w35.xlsx",
            "job_status": "completed_with_errors",
        }
    )
    assert item["import_job_id"] == 88
    assert item["template_slug"] == "distributor_inventory"
    assert item["file_name"] == "w35.xlsx"
    assert item["steward_href"] == "/admin/imports?job=88"
    assert item["covered"] is True
    assert resolution_label("product_identifier") != "product_identifier"


def test_registry_is_not_the_group_list() -> None:
    """A type can appear as a group without being in the registry."""
    groups = [
        decorate_group("product_identifier", 1, 1, 1),
        decorate_group("brand_new_token", 9, 1, 9),
    ]
    types = [g["entity_type"] for g in groups]
    assert types == ["product_identifier", "brand_new_token"]
    assert groups[1]["covered"] is False

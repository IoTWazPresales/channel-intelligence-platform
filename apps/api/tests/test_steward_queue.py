"""Steward failure-queue registry: grouping is data-driven; hrefs are config."""

from urllib.parse import parse_qs, urlparse

from app.services.imports.steward_queue import (
    STEWARD_QUEUE_RESOLUTION,
    decorate_group,
    decorate_item,
    memory_state_from_alias_count,
    resolution_href,
    resolution_label,
)


def _href_query(href: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(href).query)


def test_known_dsi_and_cst_route_to_steward_resolve_workspace() -> None:
    href = resolution_href("product_identifier", 43, normalized_key="sku-1", candidate_id=11)
    assert href is not None
    assert href.startswith("/admin/mappings?")
    q = _href_query(href)
    assert q["workspace"] == ["resolve"]
    assert q["job"] == ["43"]
    assert q["entity_type"] == ["product_identifier"]
    assert q["token"] == ["sku-1"]
    assert q["candidate"] == ["11"]
    assert "imports" not in href

    for et in (
        "customer_dealer_token",
        "distributor_token",
        "cst_product_token",
        "cst_location_token",
        "shipment_distributor",
        "shipment_customer_token",
    ):
        h = resolution_href(et, 9, normalized_key="acme")
        assert h is not None
        assert h.startswith("/admin/mappings?")
        assert _href_query(h)["workspace"] == ["resolve"]
        assert _href_query(h)["entity_type"] == [et]


def test_unknown_entity_type_is_uncovered_not_invented() -> None:
    assert "future_importer_token" not in STEWARD_QUEUE_RESOLUTION
    assert resolution_href("future_importer_token", 1) is None
    group = decorate_group("future_importer_token", 4, 2, 10)
    assert group["entity_type"] == "future_importer_token"
    assert group["label"] == "future_importer_token"
    assert group["covered"] is False
    assert group["candidate_count"] == 4


def test_decorate_item_keeps_job_as_provenance_and_deep_links_token() -> None:
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
            "memory_state": "unknown",
        }
    )
    assert item["import_job_id"] == 88
    assert item["template_slug"] == "distributor_inventory"
    assert item["file_name"] == "w35.xlsx"
    assert item["memory_state"] == "unknown"
    q = _href_query(item["steward_href"])
    assert q["workspace"] == ["resolve"]
    assert q["job"] == ["88"]
    assert q["token"] == ["sku-1"]
    assert q["candidate"] == ["7"]
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


def test_alias_count_classifies_memory_without_writing_candidates() -> None:
    assert memory_state_from_alias_count(0) == "unknown"
    assert memory_state_from_alias_count(1) == "remembered"
    assert memory_state_from_alias_count(2) == "conflict"

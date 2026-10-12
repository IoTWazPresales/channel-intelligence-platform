"""Listing quality checks from stored snapshot text. No fetch."""

from app.services.listing_capture.quality import evaluate_quality


def _takealot(**overrides):
    data = {
        "core": {"title": "ASUS ROG Ally X", "brand": "ASUS"},
        "gallery": {"images": ["a", "b", "c", "d", "e", "f"]},
        "description": {"html": " ".join(["word"] * 150)},
        "product_information": {
            "items": [
                {"display_name": "CPU"},
                {"display_name": "RAM"},
                {"display_name": "Storage"},
                {"display_name": "Screen size"},
                {"display_name": "Operating system"},
            ]
        },
        "reviews": {"count": 4},
        "buybox": {"items": [{"price": 19999, "is_add_to_cart_available": True, "stock_availability": {"status": "In stock"}}]},
    }
    data.update(overrides)
    return data


def test_takealot_pass_and_marketplace_seller_flag():
    import json

    passed = evaluate_quality(
        json.dumps(_takealot()),
        marketplace="takealot",
        product={"model_name": "ROG Ally X"},
    )
    assert passed["checks"]["buy_box"]["status"] == "pass"
    assert passed["checks"]["images"]["status"] == "pass"
    assert passed["flag_count"] == 0

    flagged = evaluate_quality(
        json.dumps(_takealot(seller_detail={"display_name": "TECHNOLAB"})),
        marketplace="takealot",
        product={"model_name": "ROG Ally X"},
    )
    assert flagged["checks"]["buy_box"]["status"] == "flag"
    assert "TECHNOLAB" in flagged["checks"]["buy_box"]["evidence"]


def test_missing_snapshot_is_no_data_not_a_flag():
    result = evaluate_quality("", marketplace="takealot", parse_status="parse_failed")
    assert result["flag_count"] == 0
    assert all(row["status"] == "no_data" for row in result["checks"].values())


def test_short_description_and_few_images_flag():
    import json

    data = _takealot()
    data["gallery"] = {"images": ["only-one"]}
    data["description"] = {"html": "too short"}
    data["reviews"] = {"count": 0}
    result = evaluate_quality(json.dumps(data), marketplace="takealot", product={"model_name": "ROG Ally X"})
    assert result["checks"]["images"]["status"] == "flag"
    assert result["checks"]["description"]["status"] == "flag"
    assert result["checks"]["reviews"]["status"] == "flag"
    assert "0 reviews" in result["checks"]["reviews"]["evidence"]


def test_amazon_is_not_checked():
    result = evaluate_quality("<html>price</html>", marketplace="amazon")
    assert result["flag_count"] == 0
    assert result["search_position"] == "deferred"
    assert all(row["status"] == "no_data" for row in result["checks"].values())

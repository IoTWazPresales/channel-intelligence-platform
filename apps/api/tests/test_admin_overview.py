from app.services.admin_overview import role_caption


def test_role_caption_keeps_zero_roles():
    assert role_caption({"admin": 1, "viewer": 1}) == "1 admin · 0 steward · 0 planner · 1 viewer"


def test_role_caption_empty():
    assert role_caption({}) == "0 admin · 0 steward · 0 planner · 0 viewer"

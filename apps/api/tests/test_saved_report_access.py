"""Unit tests for P3-4 personal/published visibility helpers."""

from app.services.saved_report_access import (
    can_edit_owned_item,
    can_view_owned_item,
    normalize_shared_roles,
    role_may_view_shared,
)


def test_published_empty_roles_visible_to_all():
    assert role_may_view_shared("viewer", []) is True
    assert role_may_view_shared("planner", None) is True


def test_published_role_gate():
    assert role_may_view_shared("viewer", ["planner"]) is False
    assert role_may_view_shared("planner", ["planner", "viewer"]) is True
    assert role_may_view_shared("admin", ["planner"]) is True


def test_personal_only_owner():
    owner = {"id": "7", "role": "planner", "tenant_id": "default"}
    other = {"id": "8", "role": "planner", "tenant_id": "default"}
    assert (
        can_view_owned_item(
            visibility="personal", owner_user_id=7, shared_roles=[], user=owner
        )
        is True
    )
    assert (
        can_view_owned_item(
            visibility="personal", owner_user_id=7, shared_roles=[], user=other
        )
        is False
    )


def test_published_role_aware():
    viewer = {"id": "9", "role": "viewer", "tenant_id": "default"}
    assert (
        can_view_owned_item(
            visibility="published",
            owner_user_id=1,
            shared_roles=["planner"],
            user=viewer,
        )
        is False
    )
    assert (
        can_view_owned_item(
            visibility="published",
            owner_user_id=1,
            shared_roles=["viewer"],
            user=viewer,
        )
        is True
    )


def test_edit_owner_or_admin():
    owner = {"id": "3", "role": "viewer"}
    admin = {"id": "1", "role": "admin"}
    other = {"id": "4", "role": "viewer"}
    assert can_edit_owned_item(owner_user_id=3, user=owner) is True
    assert can_edit_owned_item(owner_user_id=3, user=admin) is True
    assert can_edit_owned_item(owner_user_id=3, user=other) is False


def test_normalize_shared_roles():
    assert normalize_shared_roles(["VIEWER", "planner", "viewer"]) == ["viewer", "planner"]

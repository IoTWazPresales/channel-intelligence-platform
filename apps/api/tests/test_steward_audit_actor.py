"""Unit tests for steward audit actor extraction (no DB)."""

from app.services.steward_audit import _actor_fields


def test_actor_fields_session_user():
    uid, actor, tenant = _actor_fields(
        {"id": "12", "email": "a@b.co", "display_name": "Ann", "tenant_id": "default"}
    )
    assert uid == 12
    assert actor == "Ann"
    assert tenant == "default"


def test_actor_fields_stub_demo_user():
    uid, actor, tenant = _actor_fields({"id": "demo-user", "role": "admin", "tenant_id": "default"})
    assert uid is None
    assert actor == "demo-user"
    assert tenant == "default"


def test_actor_fields_none():
    uid, actor, tenant = _actor_fields(None)
    assert uid is None
    assert actor == "anonymous"
    assert tenant == "default"

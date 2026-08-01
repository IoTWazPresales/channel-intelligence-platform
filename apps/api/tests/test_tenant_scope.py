from app.core.tenant_scope import DEFAULT_TENANT_ID, tenant_id_from_user


def test_tenant_id_from_user_defaults():
    assert tenant_id_from_user(None) == DEFAULT_TENANT_ID
    assert tenant_id_from_user({}) == DEFAULT_TENANT_ID
    assert tenant_id_from_user({"tenant_id": "  "}) == DEFAULT_TENANT_ID


def test_tenant_id_from_user_explicit():
    assert tenant_id_from_user({"tenant_id": "acme"}) == "acme"

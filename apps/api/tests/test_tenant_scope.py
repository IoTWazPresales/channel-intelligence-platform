from app.core.tenant_scope import DEFAULT_TENANT_ID, tenant_id_from_user, where_tenant
from app.models.dimensions import DimProduct


def test_tenant_id_from_user_defaults():
    assert tenant_id_from_user(None) == DEFAULT_TENANT_ID
    assert tenant_id_from_user({}) == DEFAULT_TENANT_ID
    assert tenant_id_from_user({"tenant_id": "  "}) == DEFAULT_TENANT_ID


def test_tenant_id_from_user_explicit():
    assert tenant_id_from_user({"tenant_id": "acme"}) == "acme"


def test_where_tenant_compares_column():
    expr = where_tenant(DimProduct.tenant_id, {"tenant_id": "acme"})
    # SQLAlchemy binary expression — left is column, right is bound value
    assert str(expr.right.value) == "acme" or expr.right.value == "acme"

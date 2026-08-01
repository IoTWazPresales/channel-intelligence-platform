"""P2-3 auth: password helpers + role normalize (no DB)."""

from app.core.password import hash_password, verify_password
from app.core.security import Role, normalize_role


def test_password_roundtrip():
    h = hash_password("secret-pass")
    assert verify_password("secret-pass", h)
    assert not verify_password("wrong", h)


def test_normalize_role_aliases():
    assert normalize_role("admin") == Role.ADMIN
    assert normalize_role("data_steward") == Role.STEWARD
    assert normalize_role("steward") == Role.STEWARD
    assert normalize_role("commercial_manager") == Role.PLANNER
    assert normalize_role("executive_viewer") == Role.VIEWER
    assert normalize_role("unknown") == Role.VIEWER

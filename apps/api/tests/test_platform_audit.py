"""Platform audit is append-only and does not keep secrets."""

from app.services.platform_audit import scrub_audit_detail


def test_scrub_drops_password_and_token():
    clean = scrub_audit_detail(
        {
            "password": "nope",
            "new_password": "nope",
            "token": "nope",
            "sessions_revoked": True,
        }
    )
    assert clean == {"sessions_revoked": True}


def test_list_route_is_admin_only():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints" / "platform_audit.py"
    ).read_text(encoding="utf-8")
    assert "require_roles(Role.ADMIN)" in text
    assert "Role.STEWARD" not in text
    assert "Role.PLANNER" not in text

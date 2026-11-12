"""File contract for the hosted web image and the data-move runbook. No database."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WEB_DOCKERFILE = REPO / "apps" / "web" / "Dockerfile"
API_DOCKERIGNORE = REPO / "apps" / "api" / ".dockerignore"
RUNBOOK = REPO / "docs" / "PI_DATA_MOVE_RUNBOOK.md"


def test_web_image_does_not_bind_loopback():
    text = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert "127.0.0.1" not in text
    assert "0.0.0.0" in text
    assert '["pnpm", "--filter", "@cip/web", "start"]' not in text
    assert '"next", "start", "-H", "0.0.0.0"' in text


def test_api_dockerignore_keeps_secrets_and_local_env_out():
    text = API_DOCKERIGNORE.read_text(encoding="utf-8")
    for needle in (".env", ".venv", ".cip-alembic-smoke-pg"):
        assert needle in text
    assert "requirements.txt" not in text
    assert "docker-entrypoint.sh" not in text


def test_runbook_keeps_the_password_and_owner_and_names_the_revision():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "--no-owner" in text
    assert "20261105_0060" in text
    assert "password stays `cip`" in text
    assert "PG_OWNER" in text
    assert "CIP_AUTH_MODE: session" in text
    assert "ALTER TABLE" in text

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_database_wipe_status_default_disabled() -> None:
    get_settings.cache_clear()
    r = client.get("/api/v1/dev/database-wipe")
    assert r.status_code == 200
    assert r.json() == {"wipe_enabled": False}


def test_database_wipe_post_forbidden_when_disabled() -> None:
    get_settings.cache_clear()
    r = client.post("/api/v1/dev/database-wipe", json={"confirm": True})
    assert r.status_code == 403


def test_database_wipe_post_requires_confirm(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_DB_WIPE", "true")
    get_settings.cache_clear()
    try:
        r = client.post("/api/v1/dev/database-wipe", json={"confirm": False})
        assert r.status_code == 400
    finally:
        monkeypatch.delenv("ALLOW_DB_WIPE", raising=False)
        get_settings.cache_clear()


def test_database_wipe_post_runs_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_DB_WIPE", "true")
    get_settings.cache_clear()
    try:
        with patch(
            "app.api.v1.endpoints.dev_wipe.wipe_all_application_tables",
            return_value={"rows_deleted": 3},
        ) as mock_wipe:
            r = client.post("/api/v1/dev/database-wipe", json={"confirm": True})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "rows_deleted": 3}
        mock_wipe.assert_called_once()
    finally:
        monkeypatch.delenv("ALLOW_DB_WIPE", raising=False)
        get_settings.cache_clear()

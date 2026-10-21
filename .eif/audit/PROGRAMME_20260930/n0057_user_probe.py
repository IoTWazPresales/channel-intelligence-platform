"""Read-only: does admin@local exist. Prints current_database() first. No hashes."""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def probe(dbname: str) -> None:
    settings = get_settings()
    parsed = urlparse(settings.database_url_sync)
    url = urlunparse(parsed._replace(path=f"/{dbname}")).replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        db = conn.execute(text("select current_database()")).scalar_one()
        print("current_database", db)
        rows = conn.execute(
            text(
                "select email, is_active, role from app_user "
                "where lower(email) = lower(:email)"
            ),
            {"email": "admin@local"},
        ).all()
        print("matches", len(rows))
        for email, active, role in rows:
            print("user", email, "active", active, "role", role)
    engine.dispose()


def ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}/health/ready"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = json.loads(response.read().decode())
        print("ready", port, body.get("database"), body.get("ok"))
    except Exception as exc:
        print("ready", port, type(exc).__name__)


def page(port: int, path: str) -> None:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=45) as response:
            print("page", port, path, response.status)
    except Exception as exc:
        print("page", port, path, type(exc).__name__)


if __name__ == "__main__":
    ready(8001)
    ready(8002)
    page(3000, "/login")

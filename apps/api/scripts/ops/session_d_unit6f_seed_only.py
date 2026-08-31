"""Seed SESSION D unit 6f disposable rows on cip_test only (no HTTP writes)."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from scripts.ops.session_d_unit6f_cip_test_walk import (  # noqa: E402
    ACCEPT_TOKEN,
    CLEAR_TOKEN,
    CONFLICT_TOKEN,
    seed,
)


def rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def require_cip_test_api() -> None:
    with urllib.request.urlopen("http://127.0.0.1:8001/health/ready", timeout=10) as r:
        body = json.loads(r.read().decode())
    print("GET /health/ready", body)
    if body.get("database") != "cip_test":
        raise SystemExit(f"STOP: database={body.get('database')!r}")


def main() -> int:
    require_cip_test_api()
    sync = get_settings().database_url_sync
    engine = create_engine(sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test")))
    with Session(engine) as session:
        dbn = session.execute(text("SELECT current_database()")).scalar()
        print("current_database()", dbn)
        ids = seed(session)
    print("SEED_IDS", json.dumps(ids))
    print("TOKENS", ACCEPT_TOKEN, CLEAR_TOKEN, CONFLICT_TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare cip_test SESSION-D-ACCEPT line for customer-token worklist (browser 6f).

Worklist only lists lines with customer_id IS NULL. Seed sets OPEN_CHANNEL; this
prep NULLs the accept line on the latest disposable case so Accept OC + dist
appears in Customer-token stamp.
"""
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

ACCEPT_TOKEN = "SESSION-D-ACCEPT"


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
        if dbn != "cip_test":
            raise SystemExit("STOP: not cip_test")
        row = session.execute(
            text(
                "SELECT id, case_id, customer_id, distributor_attribution_status "
                "FROM commercial_lineup_line "
                "WHERE customer_token = :tok AND distributor_attribution_status = 'token_proposed' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"tok": ACCEPT_TOKEN},
        ).one_or_none()
        if row is None:
            raise SystemExit("STOP: no token_proposed SESSION-D-ACCEPT line")
        line_id, case_id, customer_id, status = row
        print("target line", line_id, "case", case_id, "customer_id", customer_id, status)
        session.execute(
            text("UPDATE commercial_lineup_line SET customer_id = NULL WHERE id = :id"),
            {"id": line_id},
        )
        deleted = session.execute(
            text(
                "DELETE FROM customer_source_token_alias "
                "WHERE normalized_token = lower(trim(:tok)) RETURNING id"
            ),
            {"tok": ACCEPT_TOKEN},
        ).fetchall()
        print("deleted aliases", deleted)
        session.commit()
        after = session.execute(
            text(
                "SELECT id, case_id, customer_id, distributor_id, distributor_attribution_status "
                "FROM commercial_lineup_line WHERE id = :id"
            ),
            {"id": line_id},
        ).one()
        print("after", tuple(after))
    with urllib.request.urlopen(
        "http://127.0.0.1:8001/api/v1/commercial-planner/lineup/customer-token/worklist?limit=20",
        timeout=15,
    ) as r:
        print("worklist", r.read().decode()[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

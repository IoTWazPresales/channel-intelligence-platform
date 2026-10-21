"""Prove a budget cap row on the cip_n0079 clone, then on cip.

Prints database name, revision, and booleans. Does not print connection strings.
Proof rows on cip are removed by the table owner after the append-only check.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

STATUS = ROOT / ".eif" / "audit" / "PROGRAMME_20261011" / "n0079_cap_status.txt"
PROOF_LINE = "__cap_proof__"
PROOF_QUARTER = "2099Q1"


def step(message: str) -> None:
    print(message, flush=True)
    with STATUS.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def owner_url(database: str):
    settings = get_settings()
    sync = make_url(sqlalchemy_sync_engine_url(settings.database_url_sync))
    try:
        import winreg
        from urllib.parse import quote

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            owner_pw, _ = winreg.QueryValueEx(key, "PG_OWNER")
    except OSError as exc:
        raise SystemExit(f"owner_secret_unavailable:{type(exc).__name__}") from exc
    if not owner_pw:
        raise SystemExit("owner_secret_empty")
    host = sync.host or "127.0.0.1"
    port = sync.port or 5432
    return make_url(
        f"postgresql+psycopg://postgres:{quote(str(owner_pw), safe='')}@{host}:{port}/{database}"
    )


def upgrade(url) -> None:
    env = os.environ.copy()
    rendered = url.render_as_string(hide_password=False)
    env["DATABASE_URL_SYNC"] = rendered
    env["DATABASE_URL_SYNC_MIGRATE"] = rendered
    env.pop("CIP_SMOKE_MIGRATE", None)
    if url.database != "cip":
        env["CIP_SMOKE_MIGRATE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").splitlines()[-4:]
        step("upgrade_failed " + " | ".join(line.strip() for line in tail if "://" not in line))
        raise SystemExit(completed.returncode)


def prove(database: str, *, cleanup: bool) -> None:
    url = owner_url(database)
    upgrade(url)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        step(f"database={current} revision={revision}")
        if current != database:
            raise SystemExit("unexpected_database")
        for amount, event_id in ((100, "cap-proof-1"), (40, "cap-proof-2"), (None, "cap-proof-3")):
            conn.execute(
                text(
                    """
                    INSERT INTO budget_ledger_entry
                        (entry_type, product_line, landed_quarter, amount_usd, source_tag, source_event_id, actor)
                    VALUES
                        ('cap', :line, :quarter, :amount, 'line_cap', :event_id, 'proof')
                    """
                ),
                {"line": PROOF_LINE, "quarter": PROOF_QUARTER, "amount": amount, "event_id": event_id},
            )
        latest = conn.execute(
            text(
                """
                SELECT amount_usd FROM budget_ledger_entry
                WHERE entry_type = 'cap' AND product_line = :line AND landed_quarter = :quarter
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"line": PROOF_LINE, "quarter": PROOF_QUARTER},
        ).scalar()
        step(f"latest_cleared={latest is None}")
        proof_id = conn.execute(
            text(
                """
                SELECT id FROM budget_ledger_entry
                WHERE product_line = :line AND entry_type = 'cap'
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"line": PROOF_LINE},
        ).scalar()
        for statement, label in (
            ("UPDATE budget_ledger_entry SET amount_usd = 1 WHERE id = :id", "update"),
            ("DELETE FROM budget_ledger_entry WHERE id = :id", "delete"),
        ):
            nested = conn.begin_nested()
            try:
                conn.execute(text(statement), {"id": proof_id})
                nested.commit()
                step(f"{label}_append_only=False")
            except SQLAlchemyError as exc:
                nested.rollback()
                step(f"{label}_append_only={'append-only' in str(exc)}")
        if cleanup:
            conn.execute(text("ALTER TABLE budget_ledger_entry DISABLE TRIGGER budget_ledger_entry_append_only"))
            conn.execute(
                text("DELETE FROM budget_ledger_entry WHERE product_line = :line AND entry_type = 'cap'"),
                {"line": PROOF_LINE},
            )
            conn.execute(text("ALTER TABLE budget_ledger_entry ENABLE TRIGGER budget_ledger_entry_append_only"))
        remaining = conn.execute(
            text("SELECT count(*) FROM budget_ledger_entry WHERE product_line = :line AND entry_type = 'cap'"),
            {"line": PROOF_LINE},
        ).scalar()
        step(f"proof_rows={remaining}")
    engine.dispose()


def main() -> None:
    STATUS.write_text("", encoding="utf-8")
    step("clone")
    prove("cip_n0079", cleanup=False)
    step("cip")
    prove("cip", cleanup=True)
    step("done")


if __name__ == "__main__":
    main()

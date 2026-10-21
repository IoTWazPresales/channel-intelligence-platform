"""Auth methods and login booleans. No secrets, no DSNs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

CANDIDATES = [
    Path(r"C:\Program Files\PostgreSQL\18\data\pg_hba.conf"),
    Path(r"C:\Program Files\PostgreSQL\17\data\pg_hba.conf"),
    Path(r"C:\Program Files\PostgreSQL\16\data\pg_hba.conf"),
]


def try_login(label: str, url: str) -> None:
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            who = conn.execute(text("SELECT current_user")).scalar()
            superuser = conn.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            ).scalar()
        print(f"{label}_ok True")
        print(f"{label}_is_postgres {who == 'postgres'}")
        print(f"{label}_super {bool(superuser)}")
    except SQLAlchemyError as exc:
        message = str(getattr(exc, "orig", exc)).lower()
        print(f"{label}_ok False")
        print(f"{label}_auth_failed {'password authentication failed' in message}")
        print(f"{label}_sspi_failed {'sspi' in message}")


def main() -> None:
    found = False
    for path in CANDIDATES:
        print(f"hba_exists {path.parent.parent.name} {path.is_file()}")
        if not path.is_file():
            continue
        found = True
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"hba_readable False {exc.__class__.__name__}")
            continue
        print("hba_readable True")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 4:
                continue
            kind = parts[0]
            method = parts[-1]
            if kind in {"local", "host", "hostssl", "hostnossl"}:
                print(f"hba {kind} {method}")
    print(f"hba_found {found}")
    try_login("sspi_postgres", "postgresql+psycopg://postgres@127.0.0.1:5432/postgres")
    try_login("sspi_windows", "postgresql+psycopg://@127.0.0.1:5432/postgres")


if __name__ == "__main__":
    main()

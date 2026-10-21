"""GATE 3 full suite on RBAC+main tree. Not for commit."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text

API = Path(r"c:\Users\warren_eliason\channel-intelligence-platform\apps\api")
PYTEST = API / ".venv" / "Scripts" / "python.exe"
ENVP = API / ".env"
TARGET_DB = "cip_test"
LOG = Path(r"c:\Users\warren_eliason\channel-intelligence-platform\.wt-main-baseline\pytest-gate3.txt")


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def dbname(url: str) -> str:
    u = url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    return (urlparse(u).path or "").lstrip("/").split("/")[0].split("?")[0]


def rewrite(url: str) -> str:
    name = dbname(url)
    if name == TARGET_DB:
        return url
    if name != "cip":
        raise SystemExit(f"refusing rewrite of unexpected db {name!r}")
    return urlunparse(urlparse(url)._replace(path="/" + TARGET_DB))


def redact(url: str) -> str:
    p = urlparse(
        url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
    )
    if not p.password:
        return url
    netloc = f"{p.username}:***@{p.hostname}"
    if p.port:
        netloc += f":{p.port}"
    return urlunparse(p._replace(netloc=netloc))


def to_psycopg(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def main() -> int:
    file_env = load_env(ENVP)
    async_url = rewrite(file_env["DATABASE_URL"])
    sync_url = rewrite(file_env["DATABASE_URL_SYNC"])
    migrate_url = rewrite(file_env.get("DATABASE_URL_SYNC_MIGRATE") or file_env["DATABASE_URL_SYNC"])
    print("DATABASE_URL=", redact(async_url), "db=", dbname(async_url))
    print("DATABASE_URL_SYNC=", redact(sync_url), "db=", dbname(sync_url))
    print("DATABASE_URL_SYNC_MIGRATE=", redact(migrate_url), "db=", dbname(migrate_url))
    engine = create_engine(to_psycopg(sync_url))
    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar()
    engine.dispose()
    print("current_database=", current)
    if current != TARGET_DB:
        raise SystemExit(f"STOP: {current}")

    child_env = os.environ.copy()
    child_env.pop("ALLOW_TESTS_ON_DEV_DB", None)
    child_env.pop("CIP_AUTH_MODE", None)
    child_env["DATABASE_URL"] = async_url
    child_env["DATABASE_URL_SYNC"] = sync_url
    child_env["DATABASE_URL_SYNC_MIGRATE"] = migrate_url
    print("child CIP_AUTH_MODE=", child_env.get("CIP_AUTH_MODE"))

    with LOG.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            [str(PYTEST), "-m", "pytest", "tests", "-q", "--tb=line"],
            cwd=str(API),
            env=child_env,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
    print(LOG.read_text(encoding="utf-8")[-9000:])
    print("=== pytest exit=", proc.returncode, "===")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())

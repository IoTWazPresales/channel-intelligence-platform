"""Disposable clone of local ``cip`` via pg_dump/pg_restore (BACKLOG-071).

Dump source may be ``cip`` (read). Restore target must never be ``cip``.

  PG_BIN                 PostgreSQL bin dir (default: Windows PG 18 path, else PATH)
  SMOKE_ADMIN_USER       superuser for createdb/dropdb (default postgres)
  SMOKE_ADMIN_PASSWORD   superuser password

Examples:

  python scripts/ops/clone_cip_db.py --clone-db cip_gate_smoke --dry-run
  python scripts/ops/clone_cip_db.py --clone-db cip_gate_smoke --drop-after
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WIN_PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
DEFAULT_SOURCE_DB = "cip"


class CloneCipError(SystemExit):
    """Abort clone-gate helper."""


def resolve_pg_bin(env: dict[str, str] | None = None) -> Path:
    src = env if env is not None else os.environ
    override = (src.get("PG_BIN") or "").strip()
    if override:
        path = Path(override)
        if not path.is_dir():
            raise CloneCipError(f"PG_BIN is not a directory: {path}")
        return path
    if os.name == "nt" and DEFAULT_WIN_PG_BIN.is_dir():
        return DEFAULT_WIN_PG_BIN
    which = shutil.which("pg_dump") or shutil.which("pg_dump.exe")
    if which:
        return Path(which).resolve().parent
    raise CloneCipError(
        "pg_dump not on PATH. Set PG_BIN to the PostgreSQL bin directory "
        r"(Windows default: C:\Program Files\PostgreSQL\18\bin)."
    )


def pg_tool(name: str, *, pg_bin: Path | None = None) -> Path:
    bin_dir = pg_bin or resolve_pg_bin()
    exe = f"{name}.exe" if os.name == "nt" else name
    path = bin_dir / exe
    if not path.is_file():
        raise CloneCipError(f"{exe} not found under {bin_dir}")
    return path


def assert_clone_db_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise CloneCipError("--clone-db is required")
    if cleaned.lower() == DEFAULT_SOURCE_DB:
        raise CloneCipError("refusing clone target database name 'cip' (writes to live cip are forbidden)")
    if not cleaned.replace("_", "").isalnum():
        raise CloneCipError(f"unsafe clone database name: {cleaned!r}")
    return cleaned


def _run(cmd: list[str], *, env: dict[str, str], label: str) -> None:
    print(f"RUN {label}: {' '.join(cmd[:8])}...")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-2000:] if result.stderr else "", file=sys.stderr)
        raise CloneCipError(f"{label} failed ({result.returncode})")


def clone_cip_database(
    *,
    clone_db: str,
    source_db: str = DEFAULT_SOURCE_DB,
    host: str = "127.0.0.1",
    port: str = "5432",
    cip_user: str = "cip",
    cip_password: str = "cip",
    dry_run: bool = False,
    drop_after: bool = False,
) -> Path:
    """Dump ``source_db`` and restore into ``clone_db``. Never restores into ``cip``."""
    target = assert_clone_db_name(clone_db)
    if source_db.strip().lower() != DEFAULT_SOURCE_DB:
        raise CloneCipError(f"source database must be {DEFAULT_SOURCE_DB!r} (got {source_db!r})")
    pg_bin = resolve_pg_bin()
    dump_path = REPO_ROOT / ".tmp" / f"{target}.dump"
    print(f"PG_BIN={pg_bin}")
    print(f"pg_dump={pg_tool('pg_dump', pg_bin=pg_bin)}")
    print(f"pg_restore={pg_tool('pg_restore', pg_bin=pg_bin)}")
    print(f"source_db={source_db} target_db={target} dump={dump_path}")
    if dry_run:
        print("dry-run: no dump/restore executed")
        return dump_path

    dump_path.parent.mkdir(parents=True, exist_ok=True)
    cip_env = os.environ.copy()
    cip_env["PGPASSWORD"] = cip_password
    admin_user = os.environ.get("SMOKE_ADMIN_USER", "postgres")
    admin_env = os.environ.copy()
    admin_env["PGPASSWORD"] = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
    if not admin_env["PGPASSWORD"]:
        raise CloneCipError("SMOKE_ADMIN_PASSWORD is required for createdb/pg_restore")

    _run(
        [
            str(pg_tool("pg_dump", pg_bin=pg_bin)),
            "-h",
            host,
            "-p",
            port,
            "-U",
            cip_user,
            "-d",
            source_db,
            "-Fc",
            "-f",
            str(dump_path),
            "--no-owner",
            "--no-privileges",
        ],
        env=cip_env,
        label="pg_dump",
    )
    _run(
        [
            str(pg_tool("dropdb", pg_bin=pg_bin)),
            "-h",
            host,
            "-p",
            port,
            "-U",
            admin_user,
            "--if-exists",
            target,
        ],
        env=admin_env,
        label="dropdb",
    )
    _run(
        [
            str(pg_tool("createdb", pg_bin=pg_bin)),
            "-h",
            host,
            "-p",
            port,
            "-U",
            admin_user,
            "-O",
            cip_user,
            target,
        ],
        env=admin_env,
        label="createdb",
    )
    _run(
        [
            str(pg_tool("pg_restore", pg_bin=pg_bin)),
            "-h",
            host,
            "-p",
            port,
            "-U",
            admin_user,
            "-d",
            target,
            "--no-owner",
            "--no-privileges",
            str(dump_path),
        ],
        env=admin_env,
        label="pg_restore",
    )
    if drop_after:
        _run(
            [
                str(pg_tool("dropdb", pg_bin=pg_bin)),
                "-h",
                host,
                "-p",
                port,
                "-U",
                admin_user,
                "--if-exists",
                target,
            ],
            env=admin_env,
            label="dropdb-after",
        )
    return dump_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone-db", required=True, help="Target database name (must not be cip)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--drop-after", action="store_true", help="Drop the clone after restore (proof only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="5432")
    args = parser.parse_args(argv)
    clone_cip_database(
        clone_db=args.clone_db,
        host=args.host,
        port=args.port,
        dry_run=args.dry_run,
        drop_after=args.drop_after,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

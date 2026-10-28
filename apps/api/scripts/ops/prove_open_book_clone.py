"""Prove the open-book close on a pg_dump clone of cip. Never writes to cip."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REPO = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

CLONE_DB = "cip_open_book_20261028"
OUT = REPO / ".eif" / "audit" / "OPEN_BOOK_20261028" / "clone_proof.txt"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _admin_password() -> None:
    if os.environ.get("SMOKE_ADMIN_PASSWORD") or os.environ.get("PG_OWNER"):
        if not os.environ.get("SMOKE_ADMIN_PASSWORD") and os.environ.get("PG_OWNER"):
            os.environ["SMOKE_ADMIN_PASSWORD"] = os.environ["PG_OWNER"]
        return
    env_path = API_ROOT / ".env"
    if not env_path.is_file():
        raise SystemExit("SMOKE_ADMIN_PASSWORD is not set")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("SMOKE_ADMIN_PASSWORD="):
            os.environ["SMOKE_ADMIN_PASSWORD"] = stripped.split("=", 1)[1].strip().strip('"')
            return
        if stripped.startswith("DATABASE_URL_SYNC_MIGRATE="):
            url = make_url(stripped.split("=", 1)[1].strip().strip('"'))
            if (url.username or "").lower() == "postgres" and url.password:
                os.environ["SMOKE_ADMIN_PASSWORD"] = url.password
                os.environ.setdefault("SMOKE_ADMIN_USER", "postgres")
                return
    raise SystemExit("SMOKE_ADMIN_PASSWORD is not set")


def _shipment_counts(database: str) -> tuple[int, int]:
    """Read-only fact counts. The caller passes either cip or the clone name."""
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    raw = make_url(get_settings().database_url_sync).set(database=database)
    engine = create_engine(sqlalchemy_sync_engine_url(raw.render_as_string(hide_password=False)))
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        total, opens = conn.execute(
            text(
                """
                SELECT count(*),
                       count(*) FILTER (WHERE lower(line_state) = 'open_order')
                FROM fact_inbound_shipment
                """
            )
        ).one()
    engine.dispose()
    return int(total), int(opens)


def _restore_existing(clone, host: str, port: str, cip_user: str, dump_path: Path) -> None:
    """Restore a dump that is already on disk. The target is the clone, never cip."""
    target = clone.assert_clone_db_name(CLONE_DB)
    admin = os.environ.get("SMOKE_ADMIN_USER", "postgres")
    env = os.environ.copy()

    def run(cmd: list[str], label: str) -> None:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            detail = ((result.stderr or "") + (result.stdout or ""))[-800:]
            raise SystemExit(f"{label} failed ({result.returncode}): {detail.strip()}")

    run(
        [str(clone.pg_tool("dropdb")), "-h", host, "-p", port, "-U", admin, "--if-exists", target],
        "dropdb",
    )
    run(
        [str(clone.pg_tool("createdb")), "-h", host, "-p", port, "-U", admin, "-O", cip_user, target],
        "createdb",
    )
    run(
        [
            str(clone.pg_tool("pg_restore")),
            "-h", host, "-p", port, "-U", admin, "-d", target,
            "--no-owner", "--no-privileges",
            str(dump_path),
        ],
        "pg_restore",
    )


def _grant_clone(clone, host: str, port: str, cip_user: str) -> None:
    """Let the application role read and write the clone. The clone is not cip."""
    admin = os.environ.get("SMOKE_ADMIN_USER", "postgres")
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
    sql = (
        f'GRANT CONNECT ON DATABASE "{CLONE_DB}" TO "{cip_user}"; '
        f'GRANT USAGE ON SCHEMA public TO "{cip_user}"; '
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{cip_user}"; '
        f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{cip_user}";'
    )
    result = subprocess.run(
        [
            str(clone.pg_tool("psql")),
            "-h", host, "-p", port, "-U", admin, "-d", CLONE_DB,
            "-v", "ON_ERROR_STOP=1", "-c", sql,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "")[-800:]
        raise SystemExit(f"grant on clone failed ({result.returncode}): {detail.strip()}")


def _drop(clone, host: str, port: str) -> None:
    admin = os.environ.get("SMOKE_ADMIN_USER", "postgres")
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
    dropdb = clone.pg_tool("dropdb")
    subprocess.run(
        [str(dropdb), "-h", host, "-p", port, "-U", admin, "--if-exists", CLONE_DB],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    if CLONE_DB.lower() == "cip":
        raise SystemExit("refusing to clone into cip")
    _admin_password()
    os.environ["PGPASSWORD"] = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
    from app.core.config import get_settings

    url = make_url(get_settings().database_url_sync)
    host = url.host or "127.0.0.1"
    port = str(url.port or 5432)
    clone = _load("clone_cip_db", REPO / "scripts" / "ops" / "clone_cip_db.py")
    close = _load("close_open_book", API_ROOT / "scripts" / "ops" / "close_open_book.py")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"clone_db={CLONE_DB}",
        "source_db=cip",
        "writes_to_cip=no",
        "pg_dump_role=superuser",
        "status=running",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        dump = REPO / ".tmp" / f"{CLONE_DB}.dump"
        if dump.is_file() and dump.stat().st_size > 1_000_000_000:
            lines.append("reused_dump=yes")
            OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
            _restore_existing(clone, host, port, url.username or "cip", dump)
        else:
            # The cip role cannot pg_dump a table with FORCE row level security.
            # The superuser dump is still a read of cip. Restore and grants stay on the clone.
            dump = clone.clone_cip_database(
                clone_db=CLONE_DB,
                host=host,
                port=port,
                cip_user=os.environ.get("SMOKE_ADMIN_USER", "postgres"),
                cip_password=os.environ.get("SMOKE_ADMIN_PASSWORD", ""),
            )
        _grant_clone(clone, host, port, url.username or "cip")
        source_rows, source_open = _shipment_counts("cip")
        clone_rows, clone_open = _shipment_counts(CLONE_DB)
        lines.append(
            f"restore_check source_rows={source_rows} source_open={source_open} "
            f"clone_rows={clone_rows} clone_open={clone_open}"
        )
        if (source_rows, source_open) != (clone_rows, clone_open):
            raise SystemExit("clone shipment counts do not match cip; refusing to apply")
        preview = close.execute(CLONE_DB, apply=False)
        applied = close.execute(CLONE_DB, apply=True)
        lines.append("dry_run=" + __import__("json").dumps(preview, default=str))
        lines.append("applied=" + __import__("json").dumps(applied, default=str))
        lines.append("result=PASS")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("result=PASS")
        print(f"wrote {OUT.name}")
        if dump.is_file():
            dump.unlink()
        return 0
    except (SystemExit, Exception) as exc:  # noqa: BLE001
        message = f"result=FAIL {type(exc).__name__}: {exc}"
        for secret in (
            os.environ.get("SMOKE_ADMIN_PASSWORD") or "",
            url.password or "",
        ):
            if secret:
                message = message.replace(secret, "[CREDENTIAL]")
        lines.append(message)
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(message)
        return 1
    finally:
        _drop(clone, host, port)


if __name__ == "__main__":
    raise SystemExit(main())

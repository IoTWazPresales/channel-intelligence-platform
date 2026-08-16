"""Refuse Alembic migrate fall-through that would mutate ``cip`` by accident.

BACKLOG-054: ``alembic/env.py`` used ``database_url_sync_migrate or database_url_sync``.
A disposable-smoke run that overrode only ``DATABASE_URL_SYNC`` still applied
revisions to ``cip`` because ``DATABASE_URL_SYNC_MIGRATE`` in ``.env`` pointed there.

Normal ``cip`` upgrades (both URLs targeting ``cip``, or migrate unset so both
resolve to the same sync URL) are unchanged.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


def _normalize_pg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def database_name_from_url(url: str) -> str:
    parsed = urlparse(_normalize_pg_url(url))
    path = (parsed.path or "").lstrip("/")
    return path.split("/")[0].split("?")[0]


def redact_database_url(url: str) -> str:
    parsed = urlparse(_normalize_pg_url(url))
    password = parsed.password
    if not password:
        return url
    netloc = parsed.netloc.replace(f":{password}@", ":***@")
    return parsed._replace(netloc=netloc).geturl()


def smoke_migrate_requested(env: dict[str, str] | None = None) -> bool:
    src = env if env is not None else os.environ
    return str(src.get("CIP_SMOKE_MIGRATE") or "").strip().lower() in {"1", "true", "yes"}


def resolve_alembic_migrate_url(
    *,
    database_url_sync: str,
    database_url_sync_migrate: str | None,
    smoke_migrate: bool | None = None,
) -> str:
    """Return the raw sync URL Alembic should use, or abort with a printed diagnostic."""
    if smoke_migrate is None:
        smoke_migrate = smoke_migrate_requested()

    explicit_migrate = (database_url_sync_migrate or "").strip() or None
    resolved = explicit_migrate or database_url_sync
    sync_db = database_name_from_url(database_url_sync)
    migrate_db = database_name_from_url(resolved)
    explicit_db = database_name_from_url(explicit_migrate) if explicit_migrate else None

    explicit_label = (
        repr(explicit_db) if explicit_migrate else "(unset — fall-through to DATABASE_URL_SYNC)"
    )
    explicit_url = redact_database_url(explicit_migrate) if explicit_migrate else "(unset)"

    def fail(msg: str) -> None:
        diagnostic = (
            "ALEMBIC MIGRATE URL GUARD FAILED\n"
            f"  {msg}\n"
            f"  DATABASE_URL_SYNC database={sync_db!r} url={redact_database_url(database_url_sync)}\n"
            f"  DATABASE_URL_SYNC_MIGRATE database={explicit_label} url={explicit_url}\n"
            f"  resolved migrate database={migrate_db!r} url={redact_database_url(resolved)}\n"
            "  Disposable smoke must set BOTH DATABASE_URL_SYNC and DATABASE_URL_SYNC_MIGRATE "
            "to the same non-cip database."
        )
        print(diagnostic, file=sys.stderr)
        raise SystemExit(diagnostic)

    if migrate_db == "cip" and sync_db != "cip":
        fail("DATABASE_URL_SYNC_MIGRATE points at cip while DATABASE_URL_SYNC points elsewhere.")

    if smoke_migrate:
        if explicit_migrate is None:
            fail(
                "CIP_SMOKE_MIGRATE=1 requires DATABASE_URL_SYNC_MIGRATE to be set explicitly "
                "(no fall-through to DATABASE_URL_SYNC)."
            )
        if sync_db == "cip" or migrate_db == "cip":
            fail("CIP_SMOKE_MIGRATE=1 refuses targeting cip.")
        if sync_db != migrate_db:
            fail("CIP_SMOKE_MIGRATE=1 requires both sync URLs to target the same disposable database.")

    return resolved

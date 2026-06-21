"""Database identity guard for one-off consolidation / preview scripts."""

from __future__ import annotations

# Local dev uses database ``cip``; Supabase-hosted CIP uses ``postgres``.
CIP_APPLICATION_DATABASE_NAMES: frozenset[str] = frozenset({"cip", "postgres"})


def is_cip_application_database(dbname: str | None) -> bool:
    return str(dbname or "").strip().lower() in CIP_APPLICATION_DATABASE_NAMES

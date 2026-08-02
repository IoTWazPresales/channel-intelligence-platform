"""Database identity guard for one-off consolidation / preview scripts."""

from __future__ import annotations

# Local dev uses database ``cip``; Supabase-hosted CIP uses ``postgres``.
CIP_APPLICATION_DATABASE_NAMES: frozenset[str] = frozenset({"cip", "postgres"})

# Ephemeral CI / smoke clones — safe targets for destructive one-off scripts in tests.
CIP_DISPOSABLE_DATABASE_NAMES: frozenset[str] = frozenset(
    {
        "cip_test",
        "cip_bulk_smoke",
        "cip_alembic_smoke",
    }
)


def is_cip_application_database(dbname: str | None) -> bool:
    """True when ``dbname`` is the app DB or an approved disposable clone (never prod-like unknowns)."""
    name = str(dbname or "").strip().lower()
    if name in CIP_APPLICATION_DATABASE_NAMES:
        return True
    if name in CIP_DISPOSABLE_DATABASE_NAMES:
        return True
    # Local clone gates: ``cip_dsi_smoke``, ``cip_lineup_smoke``, etc.
    if name.startswith("cip_") and name.endswith("_smoke"):
        return True
    return False

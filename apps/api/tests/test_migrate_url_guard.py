"""BACKLOG-054: alembic migrate URL must not silently target cip during smoke."""

from __future__ import annotations

import pytest

from app.db.migrate_url_guard import (
    database_name_from_url,
    redact_database_url,
    resolve_alembic_migrate_url,
)

CIP = "postgresql://cip:secret@127.0.0.1:5432/cip"
SMOKE = "postgresql://cip:secret@127.0.0.1:5432/cip_alembic_smoke"
OTHER = "postgresql://cip:secret@127.0.0.1:5432/cip_bulk_smoke"


def test_redact_hides_password():
    assert "***" in redact_database_url(CIP)
    assert "secret" not in redact_database_url(CIP)
    assert database_name_from_url(CIP) == "cip"


def test_normal_cip_upgrade_allows_fall_through():
    assert resolve_alembic_migrate_url(
        database_url_sync=CIP,
        database_url_sync_migrate=None,
        smoke_migrate=False,
    ) == CIP


def test_normal_cip_upgrade_allows_explicit_cip_migrate():
    assert resolve_alembic_migrate_url(
        database_url_sync=CIP,
        database_url_sync_migrate=CIP,
        smoke_migrate=False,
    ) == CIP


def test_mismatch_migrate_cip_sync_elsewhere_hard_fails():
    with pytest.raises(SystemExit) as exc:
        resolve_alembic_migrate_url(
            database_url_sync=SMOKE,
            database_url_sync_migrate=CIP,
            smoke_migrate=False,
        )
    assert "GUARD FAILED" in str(exc.value)
    assert "cip" in str(exc.value)


def test_smoke_requires_explicit_migrate_url():
    with pytest.raises(SystemExit):
        resolve_alembic_migrate_url(
            database_url_sync=SMOKE,
            database_url_sync_migrate=None,
            smoke_migrate=True,
        )


def test_smoke_refuses_cip():
    with pytest.raises(SystemExit):
        resolve_alembic_migrate_url(
            database_url_sync=CIP,
            database_url_sync_migrate=CIP,
            smoke_migrate=True,
        )


def test_smoke_ok_when_both_overridden_to_same_disposable():
    assert resolve_alembic_migrate_url(
        database_url_sync=SMOKE,
        database_url_sync_migrate=SMOKE,
        smoke_migrate=True,
    ) == SMOKE


def test_smoke_refuses_sync_and_migrate_pointing_at_different_dbs():
    with pytest.raises(SystemExit):
        resolve_alembic_migrate_url(
            database_url_sync=SMOKE,
            database_url_sync_migrate=OTHER,
            smoke_migrate=True,
        )

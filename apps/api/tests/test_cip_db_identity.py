"""CIP database identity guards for one-off scripts."""

from __future__ import annotations

from app.services.imports.cip_db_identity import is_cip_application_database


def test_is_cip_application_database_prod_names() -> None:
    assert is_cip_application_database("cip")
    assert is_cip_application_database("postgres")
    assert is_cip_application_database("CIP")


def test_is_cip_application_database_disposable_ci() -> None:
    assert is_cip_application_database("cip_test")
    assert is_cip_application_database("cip_bulk_smoke")
    assert is_cip_application_database("cip_alembic_smoke")
    assert is_cip_application_database("cip_dsi_smoke")


def test_is_cip_application_database_rejects_unknown() -> None:
    assert not is_cip_application_database("production")
    assert not is_cip_application_database("other_db")
    assert not is_cip_application_database("")

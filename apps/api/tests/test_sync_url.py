"""Sync engine URL resolution (BACKLOG-028 direct primary rewrite)."""

from __future__ import annotations

from app.core.config import Settings
from app.db.sync_url import (
    resolve_sync_engine_url,
    sqlalchemy_sync_engine_url,
    supabase_direct_primary_sync_url,
)

_POOLER = (
    "postgresql://postgres.gnhbygwvmnjwhgfskubn:secret@"
    "aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
)
_DIRECT = (
    "postgresql://postgres.gnhbygwvmnjwhgfskubn:secret@"
    "db.gnhbygwvmnjwhgfskubn.supabase.co:5432/postgres"
)


def test_supabase_direct_primary_sync_url_rewrites_pooler_5432() -> None:
    assert supabase_direct_primary_sync_url(_POOLER) == _DIRECT


def test_supabase_direct_primary_sync_url_ignores_transaction_pooler_6543() -> None:
    tx = _POOLER.replace(":5432/", ":6543/")
    assert supabase_direct_primary_sync_url(tx) is None


def test_supabase_direct_primary_sync_url_ignores_localhost() -> None:
    local = "postgresql://cip:cip@localhost:5432/cip"
    assert supabase_direct_primary_sync_url(local) is None


def test_resolve_sync_engine_url_prefers_explicit_writable() -> None:
    settings = Settings(
        database_url_sync=_POOLER,
        database_url_sync_writable=_DIRECT,
    )
    assert resolve_sync_engine_url(settings) == sqlalchemy_sync_engine_url(_DIRECT)


def test_resolve_sync_engine_url_rewrites_when_direct_primary_enabled() -> None:
    settings = Settings(
        database_url_sync=_POOLER,
        cip_supabase_sync_direct_primary=True,
    )
    assert resolve_sync_engine_url(settings) == sqlalchemy_sync_engine_url(_DIRECT)


def test_resolve_sync_engine_url_keeps_pooler_when_direct_primary_disabled() -> None:
    settings = Settings(
        database_url_sync=_POOLER,
        cip_supabase_sync_direct_primary=False,
    )
    assert resolve_sync_engine_url(settings) == sqlalchemy_sync_engine_url(_POOLER)

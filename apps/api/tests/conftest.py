"""Pytest hooks shared by API tests.

Import-pipeline integration tests create `import_job` rows, staging lines, and storage keys
under `imports/test/...` using the same `DATABASE_URL` / `DATABASE_URL_SYNC` as local dev.
When that URL targets the default database name `cip`, those tests pollute the shared dev DB.

Guard posture (deny-by-default), unless `ALLOW_TESTS_ON_DEV_DB=1` or the module is in
`_CIP_WRITE_ALLOWLIST`:

1. Setup: when settings resolve to database name `cip`, refuse every test whose module source
   names a way to open a real DB session (`_DB_ENTRY_POINT`) before any fixture runs.
2. Connect: refuse every SQLAlchemy connection to a database named `cip`, whatever path opened
   it (app services, helpers, a module the scan missed), before any SQL is sent.

There is no hand-kept list of write-capable modules: the 2026-10 leak (Import Center jobs
1672-1675 from test_dsi_customer_ignore_revalidate.py) came from modules missing from one.
Fixture-local guards (e.g. `_assert_not_cip` in bulk smoke) remain in force.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# Pin, not a fix: the suite historically assumed stub header identity (optional
# X-User-* / implicit admin) and silently inherited whatever apps/api/.env set.
# Do not edit .env or the config.py default. An explicit process CIP_AUTH_MODE
# (e.g. session for R1d e2e) wins; otherwise tests pin stub so a run is
# reproducible without ambient .env.
def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    os.environ.setdefault("CIP_AUTH_MODE", "stub")
    # Tests must never reach the live Celery broker: the always-on worker consumes the same Redis,
    # so a test's `.delay(...)` ran on the real worker (2026-10-18 18:18: reports.fanout_import_complete
    # with a MagicMock argument). Tasks sent in tests go to an in-process memory transport and are
    # never consumed. CIP_TESTS_ALLOW_LIVE_BROKER=1 is the explicit opt-out for a deliberate e2e run.
    if os.environ.get("CIP_TESTS_ALLOW_LIVE_BROKER") != "1":
        os.environ["CELERY_BROKER_URL"] = "memory://"
        os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
    from app.core.config import get_settings

    get_settings.cache_clear()
    _install_cip_connect_veto()


def pytest_report_header(config) -> list[str]:  # type: ignore[no-untyped-def]
    return [
        "CIP_AUTH_MODE pin={!r} (conftest setdefault stub; not a fix)".format(
            os.environ.get("CIP_AUTH_MODE")
        )
    ]

# Modules allowed to reach `cip` without ALLOW_TESTS_ON_DEV_DB.
# Every entry must have an inline why-comment; keep this set minimal.
_CIP_WRITE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Requires live cip via `_require_cip` — supersession restore integration against real FKs.
        "test_lineup_case_supersession_delete.py",
    }
)

# Names in a test module's source that can open a real DB session: the app's session factories
# and engines, a raw engine or driver, or the real app behind an HTTP test client.
_DB_ENTRY_POINT = re.compile(
    r"\b(?:Async)?SessionLocal\b|\bcreate(?:_async)?_engine\b|\bsync_engine\b|\bget_sync_session\b"
    r"|\bapp\.db\.session\b|\bTestClient\b|\bASGITransport\b|\bapp\.main\b|\bpsycopg\b|\basyncpg\b"
)
_opens_db_cache: dict[Path, bool] = {}

# False only while the running test's module is allowlisted; read by the connect veto.
_cip_connect_refused = True


class CipTestDatabaseRefused(pytest.fail.Exception):  # type: ignore[misc,name-defined]
    """Raised instead of connecting to `cip`. A BaseException, so app code catching Exception cannot swallow it."""


def _sqlalchemy_db_name(url: str) -> str:
    """Return the path segment after the last '/' in a SQLAlchemy-style URL (strip query string)."""
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def _cip_allowed() -> bool:
    return os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1"


def _settings_resolve_to_cip() -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    return "cip" in (_sqlalchemy_db_name(settings.database_url), _sqlalchemy_db_name(settings.database_url_sync))


def _module_opens_db(path: Path) -> bool:
    if path not in _opens_db_cache:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        # A module that cannot be read counts as able to open a session.
        _opens_db_cache[path] = not source or bool(_DB_ENTRY_POINT.search(source))
    return _opens_db_cache[path]


def _install_cip_connect_veto() -> None:
    """Refuse every SQLAlchemy connection to a database named `cip` unless the running test may use it.

    Listening on the Engine class covers every engine, sync and async, including ones built before
    this runs. Raising in `do_connect` stops before the driver connects, so no SQL reaches `cip`.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "do_connect")
    def _refuse_cip(dialect, conn_rec, cargs, cparams):  # type: ignore[no-untyped-def]
        if _cip_allowed() or not _cip_connect_refused:
            return None
        name = cparams.get("dbname") or cparams.get("database")
        if name == "cip" or (not name and _settings_resolve_to_cip()):
            raise CipTestDatabaseRefused(
                "Refusing a test connection to database 'cip' (shared dev DB). Point DATABASE_URL / "
                "DATABASE_URL_SYNC at a disposable database (e.g. .../cip_test), or set "
                "ALLOW_TESTS_ON_DEV_DB=1 to acknowledge writes to cip.",
                pytrace=False,
            )
        return None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    global _cip_connect_refused

    if _cip_allowed():
        return
    path = Path(str(getattr(item, "path", None) or item.nodeid.split("::", 1)[0]))
    _cip_connect_refused = path.name not in _CIP_WRITE_ALLOWLIST
    if not _cip_connect_refused:
        return
    if _settings_resolve_to_cip() and _module_opens_db(path):
        pytest.fail(
            f"Refusing test module {path.name!r}: database name is 'cip' (default shared dev DB) and "
            "the module can open a real DB session. Point DATABASE_URL / DATABASE_URL_SYNC at a "
            "disposable database (e.g. .../cip_test), or set ALLOW_TESTS_ON_DEV_DB=1 to acknowledge "
            "writes to the current database, or add the module to _CIP_WRITE_ALLOWLIST with a "
            "justification comment if it genuinely requires cip.",
            pytrace=False,
        )


# ---------------------------------------------------------------------------------------------
# Router-level auth (2026-09-21): app/api/v1/router.py puts get_current_user on every route.
# Contract tests that override get_db with a MagicMock never had auth in their request path
# before; in stub mode the resolver would now `await MagicMock().scalar(...)` and TypeError.
# This shim short-circuits ONLY when the injected session is not a real AsyncSession (i.e. a
# test mock) and lets get_current_user forge from headers as the stub always did. Real sessions,
# session mode, bearer tokens and forged-header handling all go through the untouched code.
# ---------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_db_safe_stub_user(monkeypatch: pytest.MonkeyPatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core import security

    original = security._resolve_stub_app_user

    async def guarded(db, x_user_id):
        if not isinstance(db, AsyncSession):
            # Returning None makes get_current_user take its own stub forge branch (missing header ->
            # ADMIN, X-User-Role/X-User-Id honoured), i.e. exactly the pre-gate behaviour without a DB.
            return None
        return await original(db, x_user_id)

    monkeypatch.setattr(security, "_resolve_stub_app_user", guarded)
    yield


# N-0037: the login throttle is process-global; clear it so one test's failures never lock another.
@pytest.fixture(autouse=True)
def _reset_login_throttle():
    from app.core.login_throttle import login_throttle

    login_throttle.reset_all()
    yield
    login_throttle.reset_all()

"""Isolated unit tests: forbid database connections, including during collection."""

import os
import sqlite3

import asyncpg
import psycopg
import pytest
import redis
from sqlalchemy.engine import Engine


_guard = pytest.MonkeyPatch()


def _refuse_connection(*args, **kwargs):
    pytest.fail("Database connections are forbidden in unit tests", pytrace=False)


def _forbid_database_connections(patch):
    # Never inherit a real database URL from local settings, even for mocked routes.
    patch.setenv("DATABASE_URL", "postgresql+asyncpg://unit:unit@127.0.0.1:1/forbidden_unit")
    patch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://unit:unit@127.0.0.1:1/forbidden_unit")
    patch.delenv("ALLOW_TESTS_ON_DEV_DB", raising=False)
    patch.setattr(Engine, "connect", _refuse_connection)
    patch.setattr(psycopg, "connect", _refuse_connection)
    patch.setattr(psycopg.Connection, "connect", _refuse_connection)
    patch.setattr(psycopg.AsyncConnection, "connect", _refuse_connection)
    patch.setattr(asyncpg, "connect", _refuse_connection)
    patch.setattr(asyncpg.connection, "connect", _refuse_connection)
    patch.setattr(sqlite3, "connect", _refuse_connection)
    patch.setattr(sqlite3.dbapi2, "connect", _refuse_connection)
    patch.setattr(redis.connection.Connection, "connect", _refuse_connection)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # Explicit isolated runs are protected during collection as well as test execution.
    # Ordinary integration-suite runs keep their existing database policy.
    if os.environ.get("CIP_UNIT_TESTS_FORBID_DB") == "1":
        _forbid_database_connections(_guard)


@pytest.fixture(autouse=True)
def _unit_tests_cannot_connect(monkeypatch):
    _forbid_database_connections(monkeypatch)


def pytest_unconfigure(config):
    _guard.undo()

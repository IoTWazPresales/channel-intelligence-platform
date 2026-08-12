"""As-of resolve for dated customer_article_alias eras (no cip)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.cst_d1 import resolve_customer_article_alias


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def test_resolve_as_of_picks_containing_era():
    early = SimpleNamespace(
        product_id=10,
        valid_from=None,
        valid_to=date(2024, 1, 1),
        status="confirmed",
    )
    late = SimpleNamespace(
        product_id=20,
        valid_from=date(2024, 1, 1),
        valid_to=None,
        status="confirmed",
    )
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([early, late])

    assert (
        resolve_customer_article_alias(
            session, customer_id=1, article_token="ART", as_of=date(2023, 6, 1)
        )
        == 10
    )
    assert (
        resolve_customer_article_alias(
            session, customer_id=1, article_token="ART", as_of=date(2024, 6, 1)
        )
        == 20
    )
    assert (
        resolve_customer_article_alias(
            session, customer_id=1, article_token="ART", as_of=date(2024, 1, 1)
        )
        == 20
    )


def test_resolve_without_as_of_prefers_open_ended():
    closed = SimpleNamespace(product_id=10, valid_from=None, valid_to=date(2024, 1, 1), status="confirmed")
    open_ended = SimpleNamespace(product_id=20, valid_from=date(2024, 1, 1), valid_to=None, status="confirmed")
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([closed, open_ended])
    assert resolve_customer_article_alias(session, customer_id=1, article_token="ART") == 20

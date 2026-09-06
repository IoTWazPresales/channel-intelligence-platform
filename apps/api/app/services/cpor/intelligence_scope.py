"""Commercial vs fixture/test cases for intelligence surfaces.

The flag is first-class on ``cpor_case.intelligence_exclude``: visible, reversible,
never a settle/steward block. Identification of the seed set is explicit case_code
membership — not ILIKE '%test%' (that matches real commercial names).
"""

from __future__ import annotations

from sqlalchemy.sql import ColumnElement

from app.models.cpor import CporCase

# Seeded by alembic 20260906_0022. Keep in sync with that migration.
SEEDED_INTELLIGENCE_EXCLUDE_CODES = frozenset(
    {
        "C26C00001",
        "BATCH0-SMOKE-001",
        "H2-SMOKE-556",
        "C23C16018",
        "C26C00002",
        "C26C00003",
        "C26C00004",
    }
)


def where_commercial_intelligence() -> ColumnElement[bool]:
    return CporCase.intelligence_exclude.is_(False)


def where_test_data_only() -> ColumnElement[bool]:
    return CporCase.intelligence_exclude.is_(True)

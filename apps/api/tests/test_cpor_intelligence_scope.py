"""Intelligence-exclude flag: explicit codes, never silent, no cip writes."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.cpor.intelligence_scope import (
    SEEDED_INTELLIGENCE_EXCLUDE_CODES,
    where_commercial_intelligence,
    where_test_data_only,
)

client = TestClient(app)


def test_seeded_codes_are_explicit_membership_not_ilike():
    assert SEEDED_INTELLIGENCE_EXCLUDE_CODES == frozenset(
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
    assert not any("%" in code for code in SEEDED_INTELLIGENCE_EXCLUDE_CODES)


def test_scope_predicates_compile():
    commercial = where_commercial_intelligence()
    test_only = where_test_data_only()
    assert commercial is not None
    assert test_only is not None
    assert str(commercial.compile(compile_kwargs={"literal_binds": True})) != str(
        test_only.compile(compile_kwargs={"literal_binds": True})
    )


def test_intelligence_exclude_requires_confirm():
    r = client.post("/api/v1/cpor/cases/1/intelligence-exclude", json={"exclude": True})
    assert r.status_code == 400
    assert "never silent" in r.json()["detail"]

"""customer_usage hard-reference checks align with ORM models."""

from app.services.customer_usage import _hard_reference_checks


def test_hard_reference_checks_includes_commercial_lineup_lines_not_case():
    labels = [label for label, _ in _hard_reference_checks(1)]
    assert "Commercial lineup lines" in labels
    assert "Commercial lineup cases" not in labels

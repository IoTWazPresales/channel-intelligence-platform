"""Unit tests for lineup bulk-protection predicate (Q-011 / BACKLOG-110/115)."""

from __future__ import annotations

import os

from app.services.commercial_planner.lineup_case_bulk_protection import (
    evaluate_case_bulk_protection,
    protected_lineup_case_ids_from_config,
)


def test_property_covers_status_and_links_without_hardcoded_ids():
    """Cases 7/90/122 shape: advanced status and/or PO links → requires_allow_protected."""
    for status, links in (
        ("po_issued", 1),
        ("po_issued", 23),
        ("po_pending", 28),
    ):
        p = evaluate_case_bulk_protection(
            case_id=999001,
            commercial_status=status,
            po_link_count=links,
            protected_ids=frozenset(),
        )
        assert p.requires_allow_protected is True
        assert p.selection_protected is True
        assert "status_advanced" in p.reasons
        assert "confirmed_po_links" in p.reasons


def test_draft_imported_no_links_only_config_catches():
    """Case 145 shape: draft_imported + 0 links → unprotected unless tenant config id."""
    bare = evaluate_case_bulk_protection(
        case_id=145,
        commercial_status="draft_imported",
        po_link_count=0,
        protected_ids=frozenset(),
    )
    assert bare.requires_allow_protected is False
    assert bare.selection_protected is False

    cfg = evaluate_case_bulk_protection(
        case_id=145,
        commercial_status="draft_imported",
        po_link_count=0,
        protected_ids=frozenset({145}),
    )
    assert cfg.requires_allow_protected is True
    assert "tenant_protected_id" in cfg.reasons


def test_contested_is_selection_only_not_service_refuse():
    """D-033: contested excludes select-all but does not require allow_protected alone."""
    p = evaluate_case_bulk_protection(
        case_id=50,
        commercial_status="draft_imported",
        po_link_count=0,
        competition_status="contested",
        protected_ids=frozenset(),
    )
    assert p.contested is True
    assert p.selection_protected is True
    assert p.requires_allow_protected is False


def test_config_ids_from_env(monkeypatch):
    monkeypatch.setenv("CIP_LINEUP_PROTECTED_CASE_IDS", "145, 7 ,bogus")
    # Clear settings cache if used
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
    ids = protected_lineup_case_ids_from_config()
    assert 145 in ids
    assert 7 in ids
    monkeypatch.delenv("CIP_LINEUP_PROTECTED_CASE_IDS", raising=False)
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass

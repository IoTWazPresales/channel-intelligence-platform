"""Failed-imports signal must list failed jobs, not the empty legacy mapping queue."""

from app.services.brief_signals import FAILED_IMPORTS_HREF, PROMO_NOT_ACTIVATED_HREF


def test_failed_imports_href_is_import_center_failed_filter() -> None:
    assert FAILED_IMPORTS_HREF == "/admin/imports?jobStatus=failed"
    assert "/admin/mappings" not in FAILED_IMPORTS_HREF



def test_promo_not_activated_href_is_activation_lens_not_activated_filter() -> None:
    assert PROMO_NOT_ACTIVATED_HREF == "/listing-capture?tab=intelligence&activation=not_activated&worklist=1"
    assert "proposed" not in PROMO_NOT_ACTIVATED_HREF

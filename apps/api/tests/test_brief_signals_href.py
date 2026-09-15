"""Failed-imports signal must list failed jobs, not the empty legacy mapping queue."""

from app.services.brief_signals import FAILED_IMPORTS_HREF


def test_failed_imports_href_is_import_center_failed_filter() -> None:
    assert FAILED_IMPORTS_HREF == "/admin/imports?jobStatus=failed"
    assert "/admin/mappings" not in FAILED_IMPORTS_HREF

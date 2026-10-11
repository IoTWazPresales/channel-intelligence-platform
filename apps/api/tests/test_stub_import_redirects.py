"""Generic Import Center must not accept a file for a template that does not apply."""

from app.api.v1.endpoints.imports import STUB_IMPORT_REDIRECTS
from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

# These slugs stay stub_noop because a dedicated surface creates the job and applies it.
DEDICATED_STUB_SLUGS = frozenset({"current_lineup", "unified_lineup", "bulk_lineup_backfill"})


def test_stub_noop_templates_are_hidden_and_do_not_accept_a_generic_upload():
    seen = set()
    for row in IMPORT_TEMPLATE_ROWS:
        if row.get("pipeline_handler") != "stub_noop":
            continue
        slug = row["slug"]
        seen.add(slug)
        assert row["hidden"] is True
        if slug in DEDICATED_STUB_SLUGS:
            assert slug not in STUB_IMPORT_REDIRECTS
            continue
        redirect = STUB_IMPORT_REDIRECTS[slug]
        assert redirect["message"]
        assert redirect["href"].startswith("/")
    assert seen
    assert set(STUB_IMPORT_REDIRECTS) == seen - DEDICATED_STUB_SLUGS

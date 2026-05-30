"""Lineup parse preview endpoint contract."""

from app.main import app


def test_parse_preview_route_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/commercial-planner/lineup-cases/{case_id}/parse-preview" in paths
    assert "/api/v1/commercial-planner/lineup-cases/{case_id}/parse-apply" in paths

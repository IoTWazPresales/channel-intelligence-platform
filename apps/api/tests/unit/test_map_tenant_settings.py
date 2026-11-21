"""Map configuration validation without a database connection."""

from __future__ import annotations

import json

import pytest

from app.services import tenant_settings as settings


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute(self, _statement, params):
        self.calls.append(params)
        return self

    def first(self):
        return None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (settings.KEY_MAP_TILEJSON, "https://tiles.example.test/tenant/tiles.json"),
        (
            settings.KEY_MAP_GLYPHS,
            "https://fonts.example.test/{fontstack}/{range}.pbf",
        ),
        (settings.KEY_MAP_ATTRIBUTION, "Tile provider © Example"),
    ],
)
def test_map_settings_use_registered_validation_and_existing_writer(key, value):
    session = RecordingSession()
    assert settings.set_setting(session, "tenant-a", key, f" {value} ", actor="steward") == value
    assert session.calls == [
        {"t": "tenant-a", "k": key, "v": json.dumps(value), "a": "steward"}
    ]


@pytest.mark.parametrize(
    "key",
    [settings.KEY_MAP_TILEJSON, settings.KEY_MAP_GLYPHS, settings.KEY_MAP_ATTRIBUTION],
)
@pytest.mark.parametrize("value", [None, "", "   "])
def test_map_settings_can_be_explicitly_cleared(key, value):
    session = RecordingSession()
    assert settings.set_setting(session, "tenant-a", key, value, actor=None) is None
    assert session.calls[0]["v"] == "null"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (settings.KEY_MAP_TILEJSON, True),
        (settings.KEY_MAP_TILEJSON, "/relative/tiles.json"),
        (settings.KEY_MAP_TILEJSON, "javascript:alert(1)"),
        (settings.KEY_MAP_TILEJSON, "https://user:password@tiles.example.test/tiles.json"),
        (settings.KEY_MAP_TILEJSON, "https://tiles.example.test:99999/tiles.json"),
        (settings.KEY_MAP_TILEJSON, "https://tiles.example.test/tiles.json#fragment"),
        (settings.KEY_MAP_TILEJSON, "https://tiles.example.test/a b"),
        (settings.KEY_MAP_TILEJSON, "https://tiles.example.test/\nprivate"),
        (settings.KEY_MAP_GLYPHS, "https://fonts.example.test/{fontstack}/font.pbf"),
        (settings.KEY_MAP_GLYPHS, "https://fonts.example.test/font/{range}.pbf"),
        (settings.KEY_MAP_ATTRIBUTION, "<img src=x onerror=alert(1)>"),
        (settings.KEY_MAP_ATTRIBUTION, "x" * 1001),
    ],
)
def test_bad_map_settings_are_refused_before_sql(key, value):
    session = RecordingSession()
    with pytest.raises(ValueError):
        settings.set_setting(session, "tenant-a", key, value, actor=None)
    assert session.calls == []


def test_missing_map_setting_has_no_default_or_seed():
    session = RecordingSession()
    assert settings.get_setting(session, "tenant-a", settings.KEY_MAP_TILEJSON) is None
    assert len(session.calls) == 1
    assert session.calls[0] == {"t": "tenant-a", "k": settings.KEY_MAP_TILEJSON}


def test_pmtiles_is_not_advertised_before_protocol_support():
    assert "map.pmtiles_url" not in settings.SETTING_VALIDATORS

"""Store place name, and an offline suggestion for where that place is.

The store code stays ``site_label``. ``place_name_from_raw`` reads the name the
file already stored. ``suggest_store_location`` matches that name, or the store
label when the file has no name, to one populated place in the bundled GeoNames
list. It does not call a geocoder and it does not write a coordinate.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

# Dual-header week band after disambiguation, e.g. ``Sales U TY 022.2026``.
_WEEK_BAND_KEY = re.compile(r"(?:^|\s)\d{1,3}[./-]\d{4}$")
_CALENDAR_DAY_KEY = "Calendar Day"
_SITE_NAME_KEY = "Site Name"
# Separators that divide a store label from its place. A space or a hyphen
# inside a name is not a separator, so the match stays exact.
_PLACE_SEPARATOR = re.compile(r"\s*[,;|/]\s*|\s+[\-\u2013\u2014]\s+")
_PLACES_PATH = Path(__file__).with_name("data") / "za_populated_places.csv"
LICENCE_NAME = "GeoNames CC BY 4.0"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def place_name_from_raw(raw: dict | None) -> str | None:
    """Return the place name for one source row, or None when the file has none.

    Named ``Site Name`` wins. A calendar-day file (a ``Calendar Day`` column) uses
    ``col_10``. A week-band file (a ``022.2026``-style column) uses ``col_11``.
    """
    if not isinstance(raw, dict):
        return None
    named = _clean(raw.get(_SITE_NAME_KEY))
    if named:
        return named
    if _CALENDAR_DAY_KEY in raw:
        return _clean(raw.get("col_10"))
    if any(_WEEK_BAND_KEY.search(str(key)) for key in raw):
        return _clean(raw.get("col_11"))
    return None


def normalise_place(value: str | None) -> str:
    """Case, accents, and punctuation fold. The letters and digits stay in order."""
    text = unicodedata.normalize("NFKC", value or "").casefold()
    folded = []
    for char in text:
        folded.append(char if char.isalnum() else " ")
    return " ".join("".join(folded).split())


def place_parts(store_label: str | None) -> list[str]:
    """Whole label, then each separator-delimited part. No substring search."""
    label = (store_label or "").strip()
    if not label:
        return []
    seen: list[str] = []
    for raw in (label, *_PLACE_SEPARATOR.split(label)):
        part = normalise_place(raw)
        if part and part not in seen:
            seen.append(part)
    return seen


class _Place:
    __slots__ = ("geonameid", "name", "latitude", "longitude")

    def __init__(self, geonameid: str, name: str, latitude: float, longitude: float) -> None:
        self.geonameid = geonameid
        self.name = name
        self.latitude = latitude
        self.longitude = longitude


@lru_cache(maxsize=1)
def _place_index() -> dict[str, tuple[_Place, ...]]:
    index: dict[str, dict[str, _Place]] = {}
    with _PLACES_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            place = _Place(
                str(row.get("geonameid") or ""),
                name,
                float(row["latitude"]),
                float(row["longitude"]),
            )
            keys = {normalise_place(name), normalise_place(row.get("ascii_name"))}
            for key in keys:
                if not key:
                    continue
                bucket = index.setdefault(key, {})
                bucket.setdefault(place.geonameid, place)
    return {key: tuple(bucket.values()) for key, bucket in index.items()}


def _manual(reason: str) -> dict[str, Any]:
    return {
        "outcome": "manual",
        "reason": reason,
        "place": None,
        "latitude": None,
        "longitude": None,
        "licence": LICENCE_NAME,
    }


def _matches(text: str | None) -> tuple[str, tuple[_Place, ...]] | None:
    """One exact place, or a marker that this text is ambiguous. None when nothing matches."""
    found: dict[str, _Place] = {}
    index = _place_index()
    for part in place_parts(text):
        hits = index.get(part)
        if not hits:
            continue
        if len(hits) != 1:
            return ("multiple", ())
        found.setdefault(hits[0].geonameid, hits[0])
    if len(found) > 1:
        return ("multiple", ())
    if len(found) == 1:
        return ("match", tuple(found.values()))
    return None


def suggest_store_location(store_label: str | None, *, place_name: str | None = None) -> dict[str, Any]:
    """Suggest one place, or send the steward to a manual pin.

    The place name from the file is the place part when the row has one. The
    store label is used as well, and on its own when the file has no place name.
    A separator-delimited part must equal one populated place after normalisation.
    No match, or more than one place, is a manual pin. Nothing is saved here.
    """
    texts: list[str] = []
    for value in (place_name, store_label):
        cleaned = (value or "").strip()
        if cleaned and cleaned not in texts:
            texts.append(cleaned)
    if not texts:
        return _manual("none")
    found: dict[str, _Place] = {}
    for text in texts:
        matched = _matches(text)
        if matched is None:
            continue
        reason, places = matched
        if reason == "multiple":
            return _manual("multiple")
        for place in places:
            found.setdefault(place.geonameid, place)
    if len(found) == 1:
        place = next(iter(found.values()))
        return {
            "outcome": "suggest",
            "reason": "match",
            "place": place.name,
            "latitude": place.latitude,
            "longitude": place.longitude,
            "licence": LICENCE_NAME,
        }
    if len(found) > 1:
        return _manual("multiple")
    return _manual("none")

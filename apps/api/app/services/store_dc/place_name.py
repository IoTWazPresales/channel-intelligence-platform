"""Store place name, and an offline proposal for where that place is.

The store code stays ``site_label``. ``place_name_from_raw`` reads the name the
file already stored. ``propose_store_pin`` finds the place inside a store label
(or the file's own place name): it drops the store's own customer-name words and
a small generic retail list, then prefers the longest exact multi-word place
name in what is left, then a fuzzy match, against the bundled GeoNames list. It
never calls a geocoder and never writes a coordinate; a steward confirms every
pin.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

# Dual-header week band after disambiguation, e.g. ``Sales U TY 022.2026``.
_WEEK_BAND_KEY = re.compile(r"(?:^|\s)\d{1,3}[./-]\d{4}$")
_CALENDAR_DAY_KEY = "Calendar Day"
_SITE_NAME_KEY = "Site Name"
# Opus R-05: the gazetteer follows the tenant country setting (``tenant.country``), never a
# built-in country. ``data/<code>_populated_places.csv``; no file for the country -> no proposals.
_PLACES_DIR = Path(__file__).with_name("data")
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
LICENCE_NAME = "GeoNames CC BY 4.0"

# Generic retail words only. No brand or chain names: the chain comes from the data
# (the customer the store belongs to), never from this list.
GENERIC_RETAIL_WORDS = frozenset(
    {
        "mall", "centre", "center", "store", "stores", "main", "shop", "shops", "branch",
        "plaza", "square", "junction", "cellular", "express", "outlet", "hyper", "super",
    }
)

# A place word directly followed by one of these names a shopping centre ("Clearwater Mall"),
# which is often far from the populated place of that name; such a match is only a weak hint.
_CENTRE_WORDS = frozenset({"mall", "centre", "center", "plaza", "square", "junction"})
_FUZZY_MIN_LENGTH = 5  # shorter words never match fuzzily
_FUZZY_MIN_RATIO = 0.86
_FUZZY_TIE = 0.02  # a different name this close to the best is an ambiguity too
_SINGLE_CONTAINED_MIN_LENGTH = 3
_SAME_PLACE_DEGREES = 0.1  # entries this close are one place, not an ambiguity
_MAX_ALTERNATIVES = 5
_MAX_WINDOW_WORDS = 4
_AMBIGUOUS_FACTOR = 0.6
_FEATURE_RANK = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4, "PPL": 5}


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
    """Case, accents, punctuation and whitespace fold. Letters and digits stay in order."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = unicodedata.normalize("NFKC", text).casefold()
    folded = [char if char.isalnum() else " " for char in text]
    return " ".join("".join(folded).split())


def _tokens(value: str | None) -> list[str]:
    return normalise_place(value).split()


def _customer_tokens(customer_names: Iterable[str | None] | None) -> set[str]:
    out: set[str] = set()
    for name in customer_names or ():
        out.update(token for token in _tokens(name) if len(token) >= 2)
    return out


def _is_customer_token(token: str, customer: set[str]) -> bool:
    if token in customer:
        return True
    # An abbreviation of one of the customer's own words ("corp" for "corporation").
    return len(token) >= 3 and any(len(word) > len(token) and word.startswith(token) for word in customer)


def significant_tokens(
    label: str | None,
    *,
    customer_names: Iterable[str | None] | None = None,
    keep_generic: bool = False,
) -> list[str]:
    """Normalised label words minus the store's own customer words, store numbers and generic retail words."""
    customer = _customer_tokens(customer_names)
    out: list[str] = []
    for token in _tokens(label):
        if len(token) < 2 or token.isdigit() or _is_customer_token(token, customer):
            continue
        if not keep_generic and token in GENERIC_RETAIL_WORDS:
            continue
        out.append(token)
    return out


class _Place:
    __slots__ = ("geonameid", "name", "latitude", "longitude", "rank")

    def __init__(self, geonameid: str, name: str, latitude: float, longitude: float, rank: int) -> None:
        self.geonameid = geonameid
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.rank = rank


class PlaceTable:
    """Normalised place name -> places, plus the fuzzy blocks. Built once, then read only."""

    def __init__(self, index: dict[str, tuple[_Place, ...]]) -> None:
        self.index = index
        self.max_words = max((key.count(" ") + 1 for key in index), default=1)
        blocks: dict[tuple[str, int], list[str]] = {}
        for key in index:
            if len(key) >= _FUZZY_MIN_LENGTH:
                blocks.setdefault((key[0], len(key)), []).append(key)
        self._blocks = blocks

    def fuzzy_candidates(self, text: str) -> Iterable[str]:
        # A typo rarely changes the first letter; the length differs by at most 2.
        for length in range(len(text) - 2, len(text) + 3):
            yield from self._blocks.get((text[0], length), ())


def build_place_table(rows: Iterable[dict[str, Any]]) -> PlaceTable:
    index: dict[str, dict[str, _Place]] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        place = _Place(
            str(row.get("geonameid") or ""),
            name,
            float(row["latitude"]),
            float(row["longitude"]),
            _FEATURE_RANK.get(str(row.get("feature_code") or ""), 6),
        )
        for key in {normalise_place(name), normalise_place(row.get("ascii_name"))}:
            if key:
                index.setdefault(key, {}).setdefault(place.geonameid, place)
    return PlaceTable(
        {key: tuple(sorted(bucket.values(), key=lambda p: p.rank)) for key, bucket in index.items()}
    )


def places_path_for_country(code: str | None) -> Path | None:
    """The bundled places file for a two-letter country code, or None when there is none."""
    clean = str(code or "").strip().upper()
    if not _COUNTRY_CODE.fullmatch(clean):
        return None
    path = _PLACES_DIR / f"{clean.lower()}_populated_places.csv"
    return path if path.is_file() else None


def place_table_for_country(code: str | None) -> PlaceTable | None:
    """The tenant country's place table (indexed once per file), or None when there is no file."""
    path = places_path_for_country(code)
    return None if path is None else _load_place_table(path)


@lru_cache(maxsize=8)
def _load_place_table(path: Path) -> PlaceTable:
    with path.open(encoding="utf-8", newline="") as handle:
        return build_place_table(csv.DictReader(handle))


# --- matching ---------------------------------------------------------------------------------


def _distinct_places(places: Iterable[_Place]) -> list[_Place]:
    """Same-named entries a few hundred metres apart count once. Best feature rank first."""
    out: list[_Place] = []
    for place in sorted(places, key=lambda p: p.rank):
        if not any(
            abs(place.latitude - other.latitude) < _SAME_PLACE_DEGREES
            and abs(place.longitude - other.longitude) < _SAME_PLACE_DEGREES
            for other in out
        ):
            out.append(place)
    return out


def _alternatives(places: list[_Place]) -> list[dict[str, Any]]:
    return [
        {"place": place.name, "latitude": place.latitude, "longitude": place.longitude}
        for place in places[:_MAX_ALTERNATIVES]
    ]


def _exact_pass(tokens: list[str], table: PlaceTable, *, min_words: int) -> tuple[str, list[_Place]] | None:
    """Longest run of tokens equal to a place name. Different runs of that length are all kept."""
    for size in range(min(table.max_words, len(tokens)), min_words - 1, -1):
        found: dict[str, tuple[_Place, ...]] = {}
        for start in range(len(tokens) - size + 1):
            key = " ".join(tokens[start : start + size])
            if size == 1 and len(key) < _SINGLE_CONTAINED_MIN_LENGTH and len(tokens) > 1:
                continue
            hits = table.index.get(key)
            if hits:
                found.setdefault(key, hits)
        if found:
            return next(iter(found)), [place for hits in found.values() for place in hits]
    return None


def _fuzzy_pass(tokens: list[str], table: PlaceTable) -> tuple[str, float, list[_Place]] | None:
    best: tuple[float, int, str] | None = None
    scored: list[tuple[float, str]] = []
    for size in range(min(_MAX_WINDOW_WORDS, len(tokens)), 0, -1):
        for start in range(len(tokens) - size + 1):
            text = " ".join(tokens[start : start + size])
            if len(text) < _FUZZY_MIN_LENGTH:
                continue
            matcher = SequenceMatcher(None, "", text, autojunk=False)
            for key in table.fuzzy_candidates(text):
                matcher.set_seq1(key)
                if matcher.real_quick_ratio() < _FUZZY_MIN_RATIO or matcher.quick_ratio() < _FUZZY_MIN_RATIO:
                    continue
                ratio = matcher.ratio()
                if ratio >= _FUZZY_MIN_RATIO:
                    scored.append((ratio, key))
                    if best is None or (ratio, size) > best[:2]:
                        best = (ratio, size, key)
    if best is None:
        return None
    ratio, _, key = best
    places = list(table.index[key])
    for other_ratio, other_key in scored:
        if other_key != key and ratio - other_ratio <= _FUZZY_TIE:
            places.extend(table.index[other_key])
    return key, ratio, places


def _confidence(method: str, *, words: int, ratio: float | None, ambiguous: bool) -> float:
    if method == "exact":
        value = 0.95 if words > 1 else 0.9
    elif method == "contained":
        value = 0.85 if words > 1 else 0.7
    else:
        value = 0.4 + 0.35 * max(0.0, min(1.0, ((ratio or 0.0) - _FUZZY_MIN_RATIO) / (1 - _FUZZY_MIN_RATIO)))
    if ambiguous:
        value *= _AMBIGUOUS_FACTOR
    return round(value, 3)


def _named_centre(key: str, loose: list[str]) -> str | None:
    """The centre name when the matched words are directly followed by a centre word, else None."""
    words = key.split()
    size = len(words)
    for start in range(len(loose) - size):
        if loose[start : start + size] == words and loose[start + size] in _CENTRE_WORDS:
            return " ".join(loose[start : start + size + 1])
    return None


def _proposal_from_text(
    text: str | None, customer_names: list[str | None], table: PlaceTable
) -> dict[str, Any] | None:
    tight = significant_tokens(text, customer_names=customer_names)
    # Generic words are kept for multi-word names only, so a place that contains one still matches.
    loose = significant_tokens(text, customer_names=customer_names, keep_generic=True)
    if not loose:
        return None
    tight_text = " ".join(tight)
    loose_text = " ".join(loose)
    found = _exact_pass(loose, table, min_words=2) if len(loose) > len(tight) else None
    if found is None and tight:
        found = _exact_pass(tight, table, min_words=1)
    ratio = None
    if found is not None:
        key, places = found
        method = "exact" if key in {tight_text, loose_text} else "contained"
    else:
        fuzzy = _fuzzy_pass(tight, table) if tight else None
        if fuzzy is None:
            return None
        key, ratio, places = fuzzy
        method = "fuzzy"
    distinct = _distinct_places(places)
    primary, others = distinct[0], distinct[1:]
    confidence = _confidence(method, words=key.count(" ") + 1, ratio=ratio, ambiguous=bool(others))
    centre = _named_centre(key, loose)
    if centre is not None:
        # BACKLOG-267: "Walmart Clearwater Mall" is a mall, not the hamlet Clearwater. Keep the
        # proposal for a steward, but never as high confidence or part of a bulk selection.
        confidence = round(confidence * _AMBIGUOUS_FACTOR, 3)
    return {
        "place": primary.name,
        "latitude": primary.latitude,
        "longitude": primary.longitude,
        "method": method,
        "confidence": confidence,
        "matched_text": key,
        "named_centre": centre,
        "ambiguous": bool(others),
        "alternatives": _alternatives(others),
    }


def propose_store_pin(
    store_label: str | None,
    *,
    place_name: str | None = None,
    customer_names: Iterable[str | None] | None = None,
    table: PlaceTable | None = None,
) -> dict[str, Any] | None:
    """One proposed place for a store, or None. Pure: nothing is saved.

    The file's own place name is tried first, then the store label. ``customer_names`` are
    the names and codes of the customer the store belongs to; their words are removed so
    the chain is never mistaken for a town.
    """
    if table is None:
        return None
    place_table = table
    names = list(customer_names or ())
    for text in (place_name, store_label):
        if not (text or "").strip():
            continue
        found = _proposal_from_text(text, names, place_table)
        if found is not None:
            return found
    return None


def _manual(reason: str) -> dict[str, Any]:
    return {
        "outcome": "manual",
        "reason": reason,
        "place": None,
        "latitude": None,
        "longitude": None,
        "method": None,
        "confidence": None,
        "matched_text": None,
        "named_centre": None,
        "ambiguous": False,
        "alternatives": [],
        "licence": LICENCE_NAME,
    }


def suggest_store_location(
    store_label: str | None,
    *,
    place_name: str | None = None,
    customer_names: Iterable[str | None] | None = None,
    table: PlaceTable | None = None,
) -> dict[str, Any]:
    """The proposal in the shape the store map sends, or a manual-pin marker. Nothing is saved.

    ``table`` is the tenant country's place table; None means no gazetteer for that country."""
    if table is None:
        return _manual("no_gazetteer_for_country")
    found = propose_store_pin(store_label, place_name=place_name, customer_names=customer_names, table=table)
    if found is None:
        return _manual("none")
    return {"outcome": "suggest", "reason": "match", **found, "licence": LICENCE_NAME}

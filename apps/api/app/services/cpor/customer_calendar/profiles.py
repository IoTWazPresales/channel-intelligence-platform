"""Mapping profile for customer campaign / pillar calendar uploads.

Same shape as the payment-evidence and historical-import profiles: a tenant-owned row of
``header_row_index`` + ``column_map_json`` (canonical field -> header aliases, first match wins) +
``value_maps_json`` (here only ``kind``). The default is a generic starting point; a tenant edits
the aliases and the kind map in the profile, nothing in code names a customer.
"""

from __future__ import annotations

from typing import Any

CALENDAR_KINDS: tuple[str, ...] = ("campaign", "pillar", "other")
DEFAULT_PROFILE_CODE = "customer_calendar_default_v1"

# Canonical fields a profile may map. name and start_date are required; end_date defaults to the
# start day; customer_token is optional when the upload names one customer for the whole file.
CALENDAR_FIELDS: tuple[str, ...] = ("customer_token", "name", "kind", "start_date", "end_date")
REQUIRED_FIELDS: tuple[str, ...] = ("name", "start_date")

_DEFAULT_COLUMN_MAP: dict[str, list[str]] = {
    "customer_token": ["Customer", "Retailer", "Account", "Customer Name"],
    "name": [
        "Name",
        "Event Name",
        "Event",
        "Campaign Name",
        "Campaign",
        "Pillar",
        "Title",
        "Description",
    ],
    "kind": ["Kind", "Type", "Event Type", "Category"],
    "start_date": ["Start", "Start Date", "From", "Begin", "Begins"],
    "end_date": ["End", "End Date", "To", "Finish", "Ends"],
}

_DEFAULT_KIND_MAP: dict[str, str] = {
    "campaign": "campaign",
    "campaigns": "campaign",
    "promo": "campaign",
    "promotion": "campaign",
    "pillar": "pillar",
    "pillars": "pillar",
    "key moment": "pillar",
    "other": "other",
}


def normalize_header(value: Any) -> str:
    """The one header comparison: case-, spacing- and non-breaking-space-insensitive.

    The parser matches file headers to saved aliases with this, profile validation uses it to
    reject one header claimed by two fields, and the web mapping editor keeps an identical copy
    (``calendarMapping.ts``) so what a user selects is what a saved mapping reads.
    """
    return " ".join(str(value or "").replace("\xa0", " ").split()).lower()


def default_calendar_profile() -> dict[str, Any]:
    """A fresh copy of the generic default profile (callers may mutate it)."""
    return {
        "profile_code": DEFAULT_PROFILE_CODE,
        "display_name": "Customer calendar (generic columns)",
        "header_row_index": 1,
        "sheet_name": None,
        "column_map_json": {k: list(v) for k, v in _DEFAULT_COLUMN_MAP.items()},
        "value_maps_json": {"kind": dict(_DEFAULT_KIND_MAP)},
        "notes": None,
    }


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Return human-readable problems; empty list means the profile can be used."""
    problems: list[str] = []
    try:
        header_row = int(profile.get("header_row_index") or 0)
    except (TypeError, ValueError):
        header_row = 0
    if header_row < 1:
        problems.append("header_row_index must be 1 or more")

    column_map = profile.get("column_map_json")
    if not isinstance(column_map, dict):
        problems.append("column_map_json must be an object of field -> header aliases")
        column_map = {}
    for field, aliases in column_map.items():
        if field not in CALENDAR_FIELDS:
            problems.append(f"column_map_json has unknown field {field!r}")
        if not isinstance(aliases, list) or not all(
            isinstance(a, str) and a.strip() for a in aliases
        ):
            problems.append(f"column_map_json[{field!r}] must be a list of non-empty header names")
    for field in REQUIRED_FIELDS:
        if not column_map.get(field):
            problems.append(f"column_map_json must map {field}")

    # One header must mean one field: an alias claimed by two fields (compared the way the parser
    # compares headers) would give one of them a column the user did not select.
    owner: dict[str, str] = {}
    for field, aliases in column_map.items():
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            key = normalize_header(alias) if isinstance(alias, str) else ""
            if not key:
                continue
            if owner.setdefault(key, field) != field:
                problems.append(
                    f"column_map_json maps header {alias.strip()!r} to more than one field "
                    f"({owner[key]}, {field})"
                )

    value_maps = profile.get("value_maps_json") or {}
    if not isinstance(value_maps, dict):
        problems.append("value_maps_json must be an object")
        value_maps = {}
    kind_map = value_maps.get("kind") or {}
    if not isinstance(kind_map, dict):
        problems.append("value_maps_json.kind must be an object of cell value -> kind")
        kind_map = {}
    for raw, kind in kind_map.items():
        if kind not in CALENDAR_KINDS:
            problems.append(
                f"value_maps_json.kind maps {raw!r} to {kind!r}; "
                f"kind must be one of {', '.join(CALENDAR_KINDS)}"
            )
    return problems

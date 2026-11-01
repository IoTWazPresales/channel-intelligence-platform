"""On the water: the voyage fields of one shipment row, read the same way by the importer and the backfill.

``voyage_fields`` takes the loosely extracted values (a mapped cell, a raw source cell) and returns the twelve
columns of ``app.models.shipment_water.ShipmentWaterColumns``: dates parsed, text trimmed to its column width,
and forwarder and origin hub read from ``shipping_method`` unless the file maps them separately.

Shipping method looks like ``COSCOckg-WWP-Truck/Sea--``: the forwarder is the leading capitals, the origin hub the
lower-case letters that follow, then the lane and mode after the first dash. The default pattern reads a
forwarder written in capitals or in a non-Latin script (``凌凱ckg-Air--``) and treats the hub as optional
(``PDHL-GS-Express--``). A tenant can replace it (named groups ``forwarder`` and, optionally, ``hub``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from app.models.shipment_water import WATER_DATE_FIELDS, WATER_FIELDS, WATER_TEXT_WIDTH

DEFAULT_SHIPPING_METHOD_PATTERN = r"^(?P<forwarder>[^\W\d_a-z]+)(?P<hub>[a-z]+)?(?=-|$)"
_DEFAULT_COMPILED = re.compile(DEFAULT_SHIPPING_METHOD_PATTERN)


def compile_shipping_method_pattern(pattern: str | None) -> re.Pattern[str]:
    """Compile a tenant pattern; ``ValueError`` when it is not a regex or has no ``forwarder`` group."""
    if pattern is None or not str(pattern).strip():
        return _DEFAULT_COMPILED
    try:
        compiled = re.compile(str(pattern).strip())
    except re.error as exc:
        raise ValueError(f"shipping_method_pattern: not a valid pattern ({exc})") from exc
    if "forwarder" not in compiled.groupindex:
        raise ValueError("shipping_method_pattern: the pattern needs a named group (?P<forwarder>...)")
    return compiled


def tenant_shipping_method_pattern(tenant_id: str = "default") -> re.Pattern[str]:
    """The tenant's pattern, or the default when none is set or the stored one is unusable."""
    from app.services.commercial_tenant_profile import load_tenant_profile_overrides

    stored = load_tenant_profile_overrides(tenant_id).get("shipping_method_pattern")
    try:
        return compile_shipping_method_pattern(stored if isinstance(stored, str) else None)
    except ValueError:
        return _DEFAULT_COMPILED


def split_shipping_method(value: str | None, pattern: re.Pattern[str] | None = None) -> tuple[str | None, str | None]:
    """(forwarder_code, origin_hub) from a shipping method; (None, None) when it does not match."""
    text = (value or "").strip()
    if not text:
        return None, None
    m = (pattern or _DEFAULT_COMPILED).match(text)
    if m is None:
        return None, None
    groups = m.groupdict()
    return (groups.get("forwarder") or None), (groups.get("hub") or None)


def _clip(value: Any, width: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.lower() in {"nan", "nat", "none", "null"}:
        return None
    return text[:width]


def voyage_fields(
    values: Mapping[str, Any],
    *,
    parse_date: Any,
    pattern: re.Pattern[str] | None = None,
) -> dict[str, str | date | None]:
    """The twelve voyage columns from loosely extracted ``values`` (missing keys read as empty).

    ``parse_date`` is the importer's own date reader (``shipment_evidence_import._parse_date``), passed in so a
    backfilled date and an imported date are parsed by one function. An explicit ``forwarder_code`` or
    ``origin_hub`` wins over the one read from the shipping method. ``ship_way`` falls back to the older
    ``shipway`` value, which saved mappings still use for the same header.
    """
    out: dict[str, str | date | None] = {}
    for name in WATER_DATE_FIELDS:
        out[name] = parse_date(values.get(name))
    for name, width in WATER_TEXT_WIDTH.items():
        out[name] = _clip(values.get(name), width)
    if out["ship_way"] is None:
        out["ship_way"] = _clip(values.get("shipway"), WATER_TEXT_WIDTH["ship_way"])
    forwarder, hub = split_shipping_method(out["shipping_method"], pattern)  # type: ignore[arg-type]
    if out["forwarder_code"] is None:
        out["forwarder_code"] = _clip(forwarder, WATER_TEXT_WIDTH["forwarder_code"])
    if out["origin_hub"] is None:
        out["origin_hub"] = _clip(hub, WATER_TEXT_WIDTH["origin_hub"])
    assert set(out) == set(WATER_FIELDS)
    return out

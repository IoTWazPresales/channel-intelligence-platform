"""Tenant overlay applied to v2 model counterparts.

The governed overlay (label, hidden, allowed grains, spec keys) lives on the
tenant profile. This module does not read SQL from that profile. Spec keys are
identifiers; the compiler binds them as parameters on one fixed ``specs_json``
extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.query.model.loader import Calculated, DataModel, Measure

SPEC_PREFIX = "spec_"
SPEC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_SPEC_KEYS = 20
_LINE_AGGS = frozenset({"avg", "min", "max"})


@dataclass(frozen=True)
class CounterpartPolicy:
    """How a tenant catalog metric restricts its v2 counterpart."""

    metric_key: str
    label: str
    hidden: bool
    grains: tuple[frozenset[str], ...] | None


def normalize_spec_keys(raw: object, *, strict: bool) -> list[str]:
    """Allowlisted top-level specs_json keys. No nested paths, no SQL."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        if strict:
            raise ValueError("semantic_overlay.spec_keys: a list of spec keys is required")
        return []
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if item is None:
            if strict:
                raise ValueError(f"semantic_overlay.spec_keys[{i}]: null is not a spec key")
            continue
        key = str(item).strip().lower()
        if "." in key:
            if strict:
                raise ValueError(
                    f"semantic_overlay.spec_keys[{i}]: {key!r} is a nested path; "
                    "only one top-level specs_json key is extracted (no cycles)"
                )
            continue
        if not SPEC_KEY_RE.fullmatch(key):
            if strict:
                raise ValueError(
                    f"semantic_overlay.spec_keys[{i}]: {key!r} is not an allowed spec key"
                )
            continue
        if key in seen:
            if strict:
                raise ValueError(f"semantic_overlay.spec_keys: duplicate key {key!r}")
            continue
        if len(out) >= MAX_SPEC_KEYS:
            if strict:
                raise ValueError(f"semantic_overlay.spec_keys: at most {MAX_SPEC_KEYS} keys")
            break
        seen.add(key)
        out.append(key)
    return out


def spec_breakdown_id(key: str) -> str:
    return f"{SPEC_PREFIX}{key}"


def spec_keys_of(catalog: object) -> tuple[str, ...]:
    raw = getattr(catalog, "spec_keys", ()) or ()
    return tuple(str(k) for k in raw)


def spec_breakdown_ids(catalog: object) -> list[str]:
    return [spec_breakdown_id(k) for k in spec_keys_of(catalog)]


def _legacy_anchor(dm: DataModel, measure: Measure | Calculated, seen: set[str]) -> Measure | None:
    if measure.id in seen:
        return None
    seen.add(measure.id)
    if isinstance(measure, Measure) and measure.legacy_key:
        return measure
    if isinstance(measure, Calculated):
        for src_id in measure.inputs:
            src = dm.measure(src_id)
            if src is None:
                continue
            found = _legacy_anchor(dm, src, seen)
            if found is not None:
                return found
        return None
    if (
        isinstance(measure, Measure)
        and measure.agg in _LINE_AGGS
        and measure.column
        and not measure.when_not_null
        and not measure.rule
    ):
        for other in dm.models[measure.model].measures.values():
            if (
                other.legacy_key
                and other.column == measure.column
                and not other.when_not_null
                and not other.rule
            ):
                return other
    return None


def counterpart_policy(dm: DataModel, measure: Measure | Calculated, catalog: object) -> CounterpartPolicy | None:
    """Hide, relabel, or narrow when the tenant catalog differs from the platform metric."""
    if catalog is None:
        return None
    anchor = _legacy_anchor(dm, measure, set())
    if anchor is None or not anchor.legacy_key:
        return None
    metric = catalog.metric_by_key(anchor.legacy_key) if hasattr(catalog, "metric_by_key") else None
    if metric is None:
        return None
    from app.semantics.registry import default_catalog

    platform = default_catalog().metric_by_key(anchor.legacy_key)
    grains: tuple[frozenset[str], ...] | None = None
    if platform is not None and set(metric.allowed_grains) != set(platform.allowed_grains):
        grains = tuple(metric.allowed_grains)
    label_changed = platform is None or metric.label != platform.label
    if not metric.hidden and grains is None and not label_changed:
        return None
    return CounterpartPolicy(
        metric_key=metric.key,
        label=metric.label,
        hidden=bool(metric.hidden),
        grains=grains,
    )


def hidden_message(policy: CounterpartPolicy) -> str:
    return (
        f"Metric {policy.label} ({policy.metric_key}) is hidden for this tenant "
        "and cannot be queried."
    )


def grain_message(policy: CounterpartPolicy, requested: frozenset[str]) -> str:
    allowed = ", ".join("{" + ", ".join(sorted(g)) + "}" for g in (policy.grains or ()))
    got = "{" + ", ".join(sorted(requested)) + "}"
    return (
        f"Metric {policy.label} ({policy.metric_key}) is limited to these breakdowns "
        f"for this tenant: {allowed}. Requested {got} is not one of them."
    )


def narrowed_breakdowns(model_breakdowns: list[str], grains: tuple[frozenset[str], ...]) -> list[str]:
    tokens: set[str] = set()
    for grain in grains:
        tokens.update(grain)
    return [b for b in model_breakdowns if b in tokens]

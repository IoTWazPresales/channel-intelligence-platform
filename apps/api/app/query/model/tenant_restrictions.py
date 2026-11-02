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


@dataclass(frozen=True)
class CounterpartPolicy:
    """How a tenant catalog metric restricts its v2 counterpart."""

    metric_key: str
    label: str
    hidden: bool
    grains: tuple[frozenset[str], ...] | None
    # True when the measure is restricted only because it reads the metric's column or takes it as an input.
    inherited: bool = False


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


def _legacy_anchors(dm: DataModel, measure: Measure | Calculated, seen: set[str]) -> list[Measure]:
    """Every legacy-keyed measure whose governed metric restricts ``measure``.

    A measure is restricted by the metric of a legacy-keyed measure when it IS that measure, when it reads the same column of
    the same model with ANY aggregate, filter or rule (``priced_units`` is the same units column with a price filter), or
    when a calculated measure takes one of them as an input (transitively). GOV-008 M6: before, only plain avg/min/max
    of the column were covered, so hiding ``sellout_units`` left ``dsi_sellout.priced_units`` queryable.
    """
    if measure.id in seen:
        return []
    seen.add(measure.id)
    if isinstance(measure, Measure) and measure.legacy_key:
        return [measure]
    if isinstance(measure, Calculated):
        found: list[Measure] = []
        for src_id in measure.inputs:
            src = dm.measure(src_id)
            if src is not None:
                found.extend(_legacy_anchors(dm, src, seen))
        return found
    if isinstance(measure, Measure) and measure.column:
        return [
            other
            for other in dm.models[measure.model].measures.values()
            if other.legacy_key and other.column == measure.column
        ]
    return []


def _anchor_policy(anchor: Measure, catalog: object, *, inherited: bool) -> CounterpartPolicy | None:
    metric = catalog.metric_by_key(anchor.legacy_key) if hasattr(catalog, "metric_by_key") else None
    if metric is None:
        return None
    from app.semantics.registry import default_catalog

    platform = default_catalog().metric_by_key(anchor.legacy_key)
    grains: tuple[frozenset[str], ...] | None = None
    if platform is not None and set(metric.allowed_grains) != set(platform.allowed_grains):
        grains = tuple(metric.allowed_grains)
    label_changed = platform is None or metric.label != platform.label
    if inherited:
        # A measure that only reads the anchor's column keeps its own label; it takes the restriction, not the name.
        if not metric.hidden and grains is None:
            return None
    elif not metric.hidden and grains is None and not label_changed:
        return None
    return CounterpartPolicy(
        metric_key=metric.key,
        label=metric.label,
        hidden=bool(metric.hidden),
        grains=grains,
        inherited=inherited,
    )


def counterpart_policy(dm: DataModel, measure: Measure | Calculated, catalog: object) -> CounterpartPolicy | None:
    """Hide, relabel, or narrow when the tenant catalog differs from the platform metric.

    The most restrictive policy of every anchor wins: hidden first; otherwise the grains every anchor allows.
    """
    if catalog is None:
        return None
    policies = [
        p
        for anchor in _legacy_anchors(dm, measure, set())
        if (p := _anchor_policy(anchor, catalog, inherited=anchor is not measure)) is not None
    ]
    if not policies:
        return None
    for p in policies:
        if p.hidden:
            return p
    narrowed = [p for p in policies if p.grains is not None]
    if not narrowed:
        return policies[0]
    grains = narrowed[0].grains
    for p in narrowed[1:]:
        grains = tuple(g for g in grains if g in p.grains)
    return CounterpartPolicy(
        metric_key=narrowed[0].metric_key, label=narrowed[0].label, hidden=False, grains=grains,
        inherited=narrowed[0].inherited,
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

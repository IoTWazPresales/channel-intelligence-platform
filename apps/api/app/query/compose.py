"""P3-1 U2 — tenant-composed metrics over existing handler-backed metrics.

v1 algebra: intra-family ratio and grain-restricted alias only. No new SQL, no
handler forks, no weighted sum, no cross-family mashup. Inputs are evaluated
through ``dispatch_handler`` (the same path platform metrics use).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.handlers import dispatch_handler, fact_family_for, handler_name_for
from app.query.types import HandlerResult, QueryRequest
from app.semantics.registry import SemanticCatalog, normalize_grains, validate_metric_grain

ALLOWED_COMPOSE_OPS = frozenset({"ratio", "alias"})


@dataclass(frozen=True)
class ComposedDef:
    id: str
    key: str
    label: str
    op: str
    inputs: tuple[str, ...]
    grain: frozenset[str]
    hidden: bool = False


def resolve_composed(metric_key: str, catalog: SemanticCatalog) -> ComposedDef | None:
    metric = catalog.metric_by_key(metric_key)
    if metric is None or metric.compose is None:
        return None
    compose = metric.compose
    return ComposedDef(
        id=metric.id,
        key=metric.key,
        label=metric.label,
        op=compose.op,
        inputs=compose.inputs,
        grain=compose.grain,
        hidden=metric.hidden,
    )


def canonicalize_compose_block(
    compose: object,
    *,
    input_grain_lookup: dict[str, tuple[frozenset[str], ...]],
    hidden_inputs: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return ``{op, inputs, grain}``. Raises ``ValueError`` on governance violation."""
    if not isinstance(compose, dict):
        raise ValueError("compose: object required")
    op = str(compose.get("op") or "").strip().lower()
    if op not in ALLOWED_COMPOSE_OPS:
        raise ValueError(
            f"compose.op {op!r} is not allowed; v1 supports only ratio and alias "
            "(no weighted sum, no other algebra)"
        )
    raw_inputs = compose.get("inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ValueError("compose.inputs: non-empty list of handler-backed metric keys required")
    inputs = [str(x).strip().lower() for x in raw_inputs if str(x).strip()]
    if len(inputs) != len(raw_inputs) or len(set(inputs)) != len(inputs):
        raise ValueError("compose.inputs: keys required and must be unique")
    if op == "alias" and len(inputs) != 1:
        raise ValueError("compose.op=alias requires exactly 1 input")
    if op == "ratio" and len(inputs) != 2:
        raise ValueError("compose.op=ratio requires exactly 2 inputs (numerator, denominator)")

    families: list[str] = []
    for key in inputs:
        if key in hidden_inputs:
            raise ValueError(f"compose.inputs: {key!r} is hidden and cannot be composed")
        family = fact_family_for(key)
        if family is None or handler_name_for(key) is None:
            raise ValueError(
                f"compose.inputs: {key!r} is not a handler-backed platform metric "
                "(composed metrics cannot input other composed metrics in v1)"
            )
        if key not in input_grain_lookup:
            raise ValueError(f"compose.inputs: {key!r} is not in the governed catalog")
        families.append(family)
    if len(set(families)) != 1:
        raise ValueError(
            "compose.inputs must share one fact family "
            "(A1 with A1, A2 with A2, A3 with A3, volume with volume); "
            "cross-family composition is not allowed"
        )

    grain = _compose_grain(compose.get("grain"))
    if not grain:
        raise ValueError("compose.grain: non-empty list of dimension ids required")
    for key in inputs:
        allowed = set(input_grain_lookup[key])
        if grain not in allowed:
            pretty = "{" + ", ".join(sorted(grain)) + "}"
            raise ValueError(
                f"compose.grain {pretty} is not an allowed grain of input {key!r} "
                "(restrict to a grain the input already accepts; never widen)"
            )
    return {"op": op, "inputs": inputs, "grain": sorted(grain)}


def _compose_grain(raw: object) -> frozenset[str]:
    """``grain`` is one set of dims, not a list of sets (that is allowed_grains)."""
    if isinstance(raw, list) and raw and all(isinstance(x, (list, tuple)) for x in raw):
        raise ValueError("compose.grain must be a single grain set [dim, ...], not [[dim], ...]")
    return normalize_grains(raw if isinstance(raw, (list, tuple, set, frozenset)) else None)


def _as_scalar(value: Any) -> float | None:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _governed_null(*, message: str, explain: dict[str, Any], invariants: list[str]) -> HandlerResult:
    return HandlerResult(
        status="ok",
        value=None,
        rows=None,
        series=None,
        scorecard=None,
        message=message,
        explain=explain,
        invariants_applied=invariants,
    )


async def evaluate_composed(
    db: AsyncSession,
    req: QueryRequest,
    composed: ComposedDef,
    catalog: SemanticCatalog,
    *,
    explain_only: bool = False,
) -> HandlerResult:
    """Evaluate a composed metric via ``dispatch_handler`` on each input. Never 500 on den==0."""
    grain_list = sorted(composed.grain)
    explain_base: dict[str, Any] = {
        "handler": "composed",
        "op": composed.op,
        "inputs": list(composed.inputs),
        "grain": grain_list,
        "metric_key": composed.key,
    }
    invariants = ["composed_intra_family", f"composed_{composed.op}"]

    if explain_only:
        return HandlerResult(
            status="ok",
            invariants_applied=invariants,
            explain=explain_base,
            message="Would evaluate composed metric from handler-backed inputs (no DB run).",
        )

    req_set = frozenset(str(g).strip().lower() for g in req.grains if str(g).strip())
    if req_set != composed.grain:
        return HandlerResult(
            status="refused",
            message=(
                f"Composed metric {composed.key} must be queried at grain "
                f"{{{', '.join(grain_list)}}}."
            ),
            explain=explain_base,
            invariants_applied=invariants,
        )

    input_rows: list[dict[str, Any]] = []
    values: list[float | None] = []
    vintages: list[dict[str, Any] | None] = []
    for input_key in composed.inputs:
        validation = validate_metric_grain(
            input_key, grain_list, catalog=catalog, tenant_id=req.tenant_id, period_grain=req.period_grain
        )
        if not validation.ok:
            return _governed_null(
                message=f"Composed input {input_key!r} is not queryable at this grain: {validation.message}",
                explain={**explain_base, "failed_input": input_key},
                invariants=invariants,
            )
        input_req = QueryRequest(
            metric=input_key,
            grains=grain_list,
            filters=dict(req.filters),
            tenant_id=req.tenant_id,
            period_grain=req.period_grain,
        )
        handler_name, hr = await dispatch_handler(
            db, input_req, metric_key=input_key, explain_only=False
        )
        scalar = _as_scalar(hr.value) if hr.status == "ok" else None
        input_rows.append(
            {
                "key": input_key,
                "handler": handler_name,
                "status": hr.status,
                "value": hr.value if hr.status == "ok" else None,
            }
        )
        values.append(scalar)
        vintages.append(hr.data_vintage if hr.status == "ok" else None)
        if hr.status != "ok":
            return _governed_null(
                message=f"Composed input {input_key!r} did not return a governed value ({hr.status}).",
                explain={**explain_base, "inputs": input_rows, "failed_input": input_key},
                invariants=invariants,
            )

    explain = {**explain_base, "inputs": input_rows}
    vintage = next((v for v in vintages if v), None)

    if composed.op == "alias":
        return HandlerResult(
            status="ok",
            value=values[0],
            data_vintage=vintage,
            explain=explain,
            invariants_applied=invariants,
            message=None if values[0] is not None else f"Alias of {composed.inputs[0]} has no scalar value.",
        )

    num, den = values[0], values[1]
    if num is None or den is None:
        return _governed_null(
            message="Composed ratio is null because an input has no scalar value.",
            explain=explain,
            invariants=invariants,
        )
    if den == 0:
        return _governed_null(
            message="Composed ratio is null because the denominator is zero.",
            explain=explain,
            invariants=invariants,
        )
    return HandlerResult(
        status="ok",
        value=num / den,
        data_vintage=vintage,
        explain=explain,
        invariants_applied=invariants,
    )

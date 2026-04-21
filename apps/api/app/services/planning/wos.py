"""Deterministic weeks-of-stock and stock risk classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WosInputs:
    on_hand: float
    avg_weekly_demand: float
    target_wos: float


def compute_wos(inputs: WosInputs) -> float:
    if inputs.avg_weekly_demand <= 0:
        return float("inf") if inputs.on_hand > 0 else 0.0
    return inputs.on_hand / inputs.avg_weekly_demand


@dataclass(frozen=True)
class StockRiskResult:
    kind: str
    explanation_summary: str
    factors: dict


def classify_stock_risk(inputs: WosInputs) -> StockRiskResult:
    wos = compute_wos(inputs)
    low = inputs.target_wos * 0.85
    high = inputs.target_wos * 1.35

    if wos == float("inf") and inputs.on_hand > 0:
        return StockRiskResult(
            kind="overstock_risk",
            explanation_summary="Demand is zero or missing while inventory exists; treat as slow mover / obsolescence risk.",
            factors={"wos": None, "target_wos": inputs.target_wos, "on_hand": inputs.on_hand},
        )

    if wos < low:
        return StockRiskResult(
            kind="stockout_risk",
            explanation_summary=(
                f"WOS {wos:.1f} is below target band (target {inputs.target_wos:.1f}, low threshold {low:.1f})."
            ),
            factors={"wos": wos, "target_wos": inputs.target_wos, "low_threshold": low},
        )

    if wos > high:
        return StockRiskResult(
            kind="overstock_risk",
            explanation_summary=(
                f"WOS {wos:.1f} exceeds high threshold {high:.1f} vs target {inputs.target_wos:.1f}."
            ),
            factors={"wos": wos, "target_wos": inputs.target_wos, "high_threshold": high},
        )

    return StockRiskResult(
        kind="healthy",
        explanation_summary=(
            f"WOS {wos:.1f} is within band around target {inputs.target_wos:.1f}."
        ),
        factors={"wos": wos, "target_wos": inputs.target_wos},
    )

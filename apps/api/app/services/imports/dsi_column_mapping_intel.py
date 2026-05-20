"""DSI import: column-level confidence, reasons, and high-confidence auto-map (shipment intel pattern)."""

from __future__ import annotations

from typing import Any

from app.ingestion.pipeline import effective_mapping_template
from app.models.ingestion import SourceDefinition
from app.services.imports.dsi_mapping_workflow import (
    DSI_MEMORY_TARGETS,
    build_initial_dsi_field_mapping,
)
from app.services.imports.pm_mapping_memory import load_by_header_norm, norm_header_key


def _norm(h: str) -> str:
    return (h or "").strip().lower()


def _memory_confidence(confirmations: int) -> float:
    return min(1.0, 0.58 + 0.07 * max(0, int(confirmations)))


def _reason_label(code: str) -> str:
    labels: dict[str, str] = {
        "source_memory": "Previously saved mapping for this feed (source memory).",
        "template_alias": "Matched an expected column alias from the import template.",
        "header_heuristic": "Matched a built-in header pattern for distributor sales & inventory files.",
        "ambiguous_targets": "Multiple plausible targets scored similarly; needs your pick.",
        "target_already_used": "Another column already maps to this target.",
        "no_match": "No confident automatic target found for this header.",
    }
    return labels.get(code, code.replace("_", " ").strip() + ".")


DSI_FIELD_TARGET_DESCRIPTIONS: dict[str, str] = {
    "distributor_token": "Distributor code or name token from the file — must resolve to a known distributor.",
    "dealer_group_token": "Primary customer account column (e.g. Dealer Name Group on RAW workbooks).",
    "customer_dealer_token": "Secondary raw customer / site label (e.g. Customer name); evidence only under the account.",
    "product_identifier": "SKU, model, part number, or other product token used for catalog matching.",
    "transaction_date": "Sell-out / invoice date for quantity sold.",
    "snapshot_date": "As-of date for stock on hand.",
    "quantity_sold": "Units sold for the transaction period.",
    "stock_on_hand": "Inventory quantity at snapshot date.",
    "unit_sellout_price_ex_tax_amount": "Unit price excluding tax/VAT for sell-out rows.",
    "reported_revenue_amount": "Line revenue or extended value from the file.",
    "currency_code": "ISO-style currency for money columns.",
    "channel_key_token": "Channel / route-to-market token from the file.",
    "region_or_province_token": "Region or province token from the file.",
    "open_channel_evidence": "Marks rows that evidence Open Channel treatment.",
    "ignored_shipping_evidence": "Shipping-like columns preserved but ignored for DSI facts.",
}


def suggest_dsi_column_mapping(
    headers: list[str],
    source: SourceDefinition | None,
    *,
    column_samples: dict[str, list[str]] | None = None,
    current_field_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Per header: suggested target, confidence, machine reasons, and a short human summary."""
    template = effective_mapping_template(source)
    aliases: dict[str, str] = {}
    for canonical, meta in template.items():
        if canonical not in DSI_MEMORY_TARGETS or not isinstance(meta, dict):
            continue
        for a in meta.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                aliases[_norm(a)] = canonical

    memory = load_by_header_norm(source) if source else {}
    baseline = build_initial_dsi_field_mapping(None, headers, source, template, column_samples=column_samples or {})
    current = dict(current_field_mapping or {})

    hints: dict[str, Any] = {}
    used_targets = set(current.values())

    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        nh = norm_header_key(col)
        scores: list[tuple[str, float, str]] = []

        mem_row = memory.get(nh) if isinstance(memory.get(nh), dict) else None
        if mem_row and mem_row.get("target"):
            tgt = str(mem_row["target"]).strip()
            if tgt in DSI_MEMORY_TARGETS:
                c = _memory_confidence(int(mem_row.get("confirmations") or 0))
                scores.append((tgt, c, "source_memory"))

        key = _norm(col)
        if key in aliases:
            at = aliases[key]
            scores.append((at, 0.96, "template_alias"))

        heur = baseline.get(col)
        if heur and heur in DSI_MEMORY_TARGETS:
            scores.append((heur, 0.84, "header_heuristic"))

        merged: dict[str, tuple[float, str]] = {}
        for tgt, sc, tag in scores:
            prev = merged.get(tgt)
            if prev is None or sc > prev[0]:
                merged[tgt] = (sc, tag)

        ranked = sorted(((t, merged[t][0], merged[t][1]) for t in merged), key=lambda x: x[1], reverse=True)
        best_t, best_s, best_tag = ranked[0] if ranked else (None, 0.0, "")
        second_s = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_t and best_t in used_targets and col not in current:
            hints[col] = {
                "suggested_target": None,
                "confidence": 0.0,
                "reasons": ["target_already_used"],
                "reason_summary": _reason_label("target_already_used"),
                "runner_up": None,
            }
            continue

        if not best_t or best_s < 0.2:
            hints[col] = {
                "suggested_target": None,
                "confidence": 0.0,
                "reasons": ["no_match"],
                "reason_summary": _reason_label("no_match"),
                "runner_up": None,
            }
            continue

        margin = best_s - second_s
        if second_s >= 0.25 and margin < 0.12:
            hints[col] = {
                "suggested_target": best_t,
                "confidence": round(min(0.82, best_s * 0.85), 3),
                "reasons": ["ambiguous_targets"],
                "reason_summary": _reason_label("ambiguous_targets"),
                "runner_up": ranked[1][0] if len(ranked) > 1 else None,
            }
            continue

        conf = round(min(0.99, best_s + min(0.08, margin * 0.15)), 3)
        primary_reason = best_tag or "header_heuristic"
        signal_tags = sorted({x[2] for x in scores})

        samp = (column_samples or {}).get(col) if column_samples else None
        hints[col] = {
            "suggested_target": best_t,
            "confidence": conf,
            "reasons": signal_tags[:8],
            "reason_summary": _reason_label(primary_reason),
            "runner_up": ranked[1][0] if len(ranked) > 1 else None,
            "sample_values": (samp or [])[:5] if isinstance(samp, list) else [],
        }

    return hints


def apply_high_confidence_dsi_automap(
    headers: list[str],
    source: SourceDefinition | None,
    base_mapping: dict[str, str],
    *,
    column_samples: dict[str, list[str]] | None = None,
    min_confidence: float = 0.9,
) -> tuple[dict[str, str], list[str]]:
    """Fill unmapped headers when suggestion confidence is high and target is unused."""
    hints = suggest_dsi_column_mapping(
        headers, source, column_samples=column_samples, current_field_mapping=base_mapping
    )
    out = dict(base_mapping)
    used = set(out.values())
    applied: list[str] = []
    for h, meta in hints.items():
        if h in out and out[h]:
            continue
        tgt = meta.get("suggested_target")
        conf = float(meta.get("confidence") or 0.0)
        if not tgt or conf < min_confidence:
            continue
        if tgt in used:
            continue
        out[str(h)] = str(tgt)
        used.add(str(tgt))
        applied.append(f"{h}→{tgt}")
    return out, applied

"""AI summary of the sell-through overview (Warren 2026-10-19).

The numbers are always computed by ``sell_through_overview``; the model only words them. It gets a
compact fact sheet (about 1-2k tokens: headline numbers, best sellers, the most urgent SKU problems,
missing reports), never raw rows, and is told to use no figure that is not in the sheet.

Token use is kept small: one call per filter set, cached for ``ai_narrative_cache_minutes``, a low
effort setting and a short answer. When AI assist is off, the key is missing or the call fails, the
rule-based summary is returned instead, labelled as such.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You write the short summary at the top of a retail sell-through dashboard for a consumer "
    "electronics vendor's channel team. You are given a JSON fact sheet computed by the system. "
    "Write 4 to 6 plain sentences: what changed, what is selling, what needs action (restock, "
    "sales drops, aged stock), the possible causes the facts list for them, and which customer "
    "reports are missing. Lead with the most important "
    "point. Use only numbers and names that appear in the fact sheet; do not estimate or invent "
    "figures, causes or recommendations beyond what the facts support. No headings, no bullet "
    "points, no markdown."
)
_MAX_TOKENS = 2000

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def fact_sheet(overview: dict[str, Any]) -> dict[str, Any]:
    """The compact facts the model sees. Rounded and trimmed to keep the prompt small."""
    k = overview["kpis"]
    f = overview["filters"]
    problems = overview["problems"]["rows"]

    def r(v: Any) -> Any:
        return round(v, 1) if isinstance(v, float) else v

    def pct(v: float | None) -> str | None:
        return None if v is None else f"{v * 100:+.0f}%"

    return {
        "window": f"{f['date_from']} to {f['date_to']}",
        "compared_with": f["compare"] if f["compare"] != "none" else None,
        "units": r(k["units"]),
        "units_change": pct(k["units_change_pct"]),
        "sales_value": r(k["value"]),
        "sales_value_vat": "incl. VAT" if f["vat"] == "inc_vat" else "excl. VAT",
        "value_change": pct(k["value_change_pct"]),
        "stock_at_customers": r(k["stock_on_hand"]),
        "weeks_of_cover": k["weeks_of_cover"],
        "best_sellers": [
            {"product": t["label"], "units": r(t["units"]), "change": pct(t["change_pct"])}
            for t in overview["top_sellers"][:5]
        ],
        "by_customer": [{"customer": c["name"], "units": r(c["units"])} for c in overview["customer_split"][:6]],
        "sku_problem_counts": overview["problems"]["counts"],
        "most_urgent_skus": [
            {"why": p["reason_label"], "customer": p["customer_name"], "product": p["product"], "detail": p["detail"],
             "suggested_order": p["suggested_qty"],
             "possible_causes": [f"{c['label']}: {c['detail']}" for c in (p.get("causes") or [])[:3]]}
            for p in problems[:8]
        ],
        "quarters_vs_last_year": [
            {"quarter": q["label"], "units": r(q["units"]), "last_year": r(q["last_year_units"]), "partial": q["partial"]}
            for q in overview["quarters"]
        ],
        "customers_with_missing_reports": overview["coverage"]["customers_missing"][:8],
    }


def _rules(overview: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"source": "rules", "text": " ".join(overview.get("summary") or []), "reason": reason}


def narrate(overview: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ai_assist_enabled:
        return _rules(overview, "AI assist is off in this installation")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _rules(overview, "No Anthropic API key is set on the server")

    facts = fact_sheet(overview)
    body = json.dumps(facts, sort_keys=True, separators=(",", ":"), default=str)
    model = settings.ai_narrative_model
    key = hashlib.sha256(f"{tenant_id}|{model}|{body}".encode()).hexdigest()
    ttl = settings.ai_narrative_cache_minutes * 60
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return {**hit[1], "cached": True}

    try:
        import anthropic
    except ImportError:
        return _rules(overview, "The anthropic package is not installed on the server")

    client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            output_config={"effort": "low"},
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Fact sheet:\n{body}"}],
        )
    except anthropic.RateLimitError:
        return _rules(overview, "The AI service is busy; try again shortly")
    except anthropic.AuthenticationError:
        logger.warning("Sell-through summary: the Anthropic API key was refused")
        return _rules(overview, "The server's Anthropic API key was refused")
    except anthropic.APIStatusError as exc:
        logger.warning("Sell-through summary: API error %s", exc.status_code)
        return _rules(overview, f"The AI service returned an error ({exc.status_code})")
    except anthropic.APIConnectionError:
        return _rules(overview, "The AI service could not be reached")
    except TypeError:  # an anthropic package too old for output_config
        return _rules(overview, "The server's anthropic package is too old; update it")

    if msg.stop_reason == "refusal":
        return _rules(overview, "The AI service declined this summary")
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text").strip()
    if not text:
        return _rules(overview, "The AI service returned no text")
    usage = getattr(msg, "usage", None)
    out = {
        "source": "ai",
        "text": text,
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (now, out)
    return out

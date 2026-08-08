"""Observation snapshot compress/parse + rate-limit helpers (mocked HTTP in tests)."""

from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.services.listing_capture.marketplace_vocab import PARSER_VERSION

LISTING_CAPTURE_USER_AGENT = "CIP-listing-capture/1.0"
LISTING_CAPTURE_HTTP_TIMEOUT_SECONDS = 20

# Polite defaults (seconds between fetches per marketplace).
RATE_LIMIT_SECONDS: dict[str, float] = {
    "takealot": 2.0,
    "evetech": 2.0,
}

# Dead-link backoff: after N consecutive 404/410, wait this many hours before retry.
DEAD_LINK_BACKOFF_HOURS = 24
DEAD_LINK_CONSECUTIVE_THRESHOLD = 3


def compress_snapshot(raw: str | bytes) -> bytes:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return gzip.compress(raw)


def decompress_snapshot(blob: bytes | None) -> str:
    if not blob:
        return ""
    return gzip.decompress(blob).decode("utf-8", errors="replace")


@dataclass
class ParseResult:
    parse_status: str
    price: float | None = None
    availability: str | None = None
    promo_badge: str | None = None
    flags: dict[str, Any] | None = None


def parse_snapshot_text(text: str, *, marketplace: str, parser_version: str = PARSER_VERSION) -> ParseResult:
    """Minimal v0 parsers — JSON preferred; HTML price regex fallback. FLAG on failure."""
    flags: dict[str, Any] = {"parser_version": parser_version, "marketplace": marketplace}
    if not text.strip():
        return ParseResult(parse_status="parse_failed", flags={**flags, "reason": "empty_snapshot"})

    # Try JSON envelope first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            price = data.get("price")
            return ParseResult(
                parse_status="ok",
                price=float(price) if price is not None else None,
                availability=str(data.get("availability") or "") or None,
                promo_badge=str(data.get("promo_badge") or "") or None,
                flags=flags,
            )
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    m = re.search(r"(?:R\s*)?(\d[\d\s]*[.,]\d{2}|\d+)", text)
    if m:
        raw_num = m.group(1).replace(" ", "").replace(",", "")
        try:
            return ParseResult(
                parse_status="ok",
                price=float(raw_num),
                availability="unknown",
                flags={**flags, "method": "html_regex"},
            )
        except ValueError:
            pass

    return ParseResult(parse_status="parse_failed", flags={**flags, "reason": "no_price_found"})


def should_backoff_dead_link(
    *,
    consecutive_dead: int,
    last_fetch_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    if consecutive_dead < DEAD_LINK_CONSECUTIVE_THRESHOLD:
        return False
    if last_fetch_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now < last_fetch_at + timedelta(hours=DEAD_LINK_BACKOFF_HOURS)


def default_http_get(url: str) -> tuple[int, str]:
    """Live HTTP fetch — only invoked when the caller explicitly enables live fetch (P5).

    Uses urllib (stdlib, no new dependency) with a declared User-Agent and a bounded
    timeout so a slow/unreachable marketplace host cannot hang the beat task.
    """
    request = urllib.request.Request(url, headers={"User-Agent": LISTING_CAPTURE_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=LISTING_CAPTURE_HTTP_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", None) or response.getcode())
            body = response.read().decode("utf-8", errors="replace")
            return status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), body
    except urllib.error.URLError:
        return 0, ""


def fetch_url_text(
    url: str,
    *,
    http_get: Callable[[str], tuple[int, str]] | None = None,
) -> tuple[int, str]:
    """Fetch listing page. Production path injects http_get; default raises (no live HTTP in unit)."""
    if http_get is None:
        raise RuntimeError("Live HTTP disabled in LC-U1 — inject http_get mock")
    return http_get(url)

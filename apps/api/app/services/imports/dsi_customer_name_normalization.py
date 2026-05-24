"""Customer/dealer display-name normalisation for DSI duplicate detection and matching."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Legal / trading suffixes and noise (order: longer phrases first).
_LEGAL_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\(\s*pty\s*\)\s*ltd\.?",
        r"\(\s*pty\s*\)",
        r"\bpty\.?\s*ltd\.?",
        r"\bproprietary\s+limited\b",
        r"\bclose\s+corporation\b",
        r"\bn\.?p\.?c\.?\b",
        r"\bincorporated\b",
        r"\blimited\b",
        r"\bcompany\b",
        r"\bcorp\.?\b",
        r"\binc\.?\b",
        r"\bltd\.?\b",
        r"\bllc\.?\b",
        r"\bnpc\b",
        r"\bcc\b",
    )
)

_TRADING_AS = re.compile(
    r"\b(?:t/a|a/t|trading\s+as|ta:)\s+",
    re.IGNORECASE,
)


def normalize_customer_name_for_similarity(raw: str | None) -> str:
    """Strip legal suffixes and noise, lowercase, collapse whitespace — for duplicate/compare only."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _TRADING_AS.sub(" ", s)
    for pat in _LEGAL_SUFFIX_PATTERNS:
        s = pat.sub(" ", s)
    s = re.sub(r"[,;]+", " ", s)
    s = re.sub(r"[.()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_customer_name_token(raw: str | None) -> str:
    """Normalised token stored on candidate context for downstream matching (may be empty)."""
    return normalize_customer_name_for_similarity(raw)


# Industry / legal noise tokens — not used alone to flag duplicates (avoids "X Technologies" vs "Y Technologies").
_GENERIC_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "technologies",
        "technology",
        "tech",
        "solutions",
        "solution",
        "services",
        "service",
        "systems",
        "system",
        "electronics",
        "electronic",
        "computers",
        "computer",
        "holdings",
        "holding",
        "group",
        "international",
        "global",
        "distribution",
        "distributors",
        "distributor",
        "enterprises",
        "enterprise",
        "industries",
        "industry",
        "wholesale",
        "retail",
        "logistics",
        "supply",
        "supplies",
        "trading",
        "company",
        "co",
        "pty",
        "ltd",
        "limited",
        "inc",
        "corp",
        "llc",
        "cc",
        "npc",
        "proprietary",
        "close",
        "corporation",
        "incorporated",
    }
)

# Cascade thresholds (see ``dsi_duplicate_similarity_score``).
DSI_DUPLICATE_DISTINCTIVE_THRESHOLD: float = 0.90
DSI_DUPLICATE_DISTINCTIVE_EXACT_CUTOFF: float = 0.98
DSI_DUPLICATE_FULL_STRING_THRESHOLD: float = 0.88
DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD: float = 0.72
DSI_DUPLICATE_MIN_NORMALIZED_LEN: int = 4
DSI_DUPLICATE_MIN_DISTINCTIVE_LEN: int = 3

# Single-token edits (nrc vs ngr) with short shared prefix — suppress unless prefix >= 2 chars.
_DUPLICATE_SUPPRESS_MAX_TOKEN_LEN: int = 4
_DUPLICATE_SUPPRESS_MIN_SHARED_PREFIX: int = 2


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return la + lb
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[lb]


def _one_edit_apart(a: str, b: str) -> bool:
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = edits = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            edits += 1
            if edits > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            else:
                j += 1
    return edits + (lb - j) <= 1


def _shared_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _distinctive_short_token_flip_should_suppress(dist_a: str, dist_b: str) -> bool:
    """Suppress OCR-style single-token flips (e.g. nrc vs ngr), not it vs its."""
    ta = dist_a.split()
    tb = dist_b.split()
    if not ta or len(ta) != len(tb):
        return False
    flip_at: list[int] = [i for i in range(len(ta)) if ta[i] != tb[i]]
    if len(flip_at) != 1:
        return False
    i = flip_at[0]
    a, b = ta[i], tb[i]
    if len(a) > _DUPLICATE_SUPPRESS_MAX_TOKEN_LEN or len(b) > _DUPLICATE_SUPPRESS_MAX_TOKEN_LEN:
        return False
    if not _one_edit_apart(a, b):
        # Two single-char OCR substitutions on a 3-letter token (nrc vs ngr).
        if len(a) == len(b) == 3 and a[0] == b[0] and _levenshtein_distance(a, b) == 2:
            return True
        return False
    # Same-length 3–4 char tokens differing only in the last character.
    if len(a) == len(b) and 3 <= len(a) <= 4 and _shared_prefix_len(a, b) == len(a) - 1:
        return True
    return _shared_prefix_len(a, b) < _DUPLICATE_SUPPRESS_MIN_SHARED_PREFIX


def _leading_distinctive_token_variant(dist_a: str, dist_b: str) -> bool:
    """True when first distinctive token matches and second differs by it/its-style edit (cloud it cases)."""
    ta = dist_a.split()
    tb = dist_b.split()
    if len(ta) < 2 or len(tb) < 2 or ta[0] != tb[0]:
        return False
    if not _one_edit_apart(ta[1], tb[1]):
        return False
    return abs(len(ta[1]) - len(tb[1])) <= 1 and min(len(ta[1]), len(tb[1])) >= 2


def split_distinctive_and_generic_tokens(normalized: str) -> tuple[str, str]:
    """Split normalised display name into distinctive stem vs generic/industry tail tokens."""
    tokens = (normalized or "").split()
    distinctive = [t for t in tokens if t not in _GENERIC_NAME_TOKENS and len(t) >= 2]
    generic = [t for t in tokens if t in _GENERIC_NAME_TOKENS]
    return " ".join(distinctive), " ".join(generic)


def _leading_distinctive_token(normalized: str) -> str:
    """First non-generic token (len >= 2) in normalised display name."""
    for t in (normalized or "").split():
        if t not in _GENERIC_NAME_TOKENS and len(t) >= 2:
            return t
    return ""


def _remainder_after_short_leading_prefix(normalized: str, lead_token: str) -> str:
    """Drop the short leading distinctive token, then generic tokens from the tail."""
    tokens = (normalized or "").split()
    if not tokens or tokens[0] != lead_token:
        return ""
    tail = [t for t in tokens[1:] if t not in _GENERIC_NAME_TOKENS]
    return " ".join(tail)


def _token_prefix_extension_score(
    left: str,
    right: str,
    *,
    min_short_len: int,
    full_string_threshold: float,
) -> float | None:
    """Score when the shorter string is a whole-token prefix of the longer (e.g. barak / barakah)."""
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    if len(short) < min_short_len:
        return None
    if short != long and not long.startswith(short):
        return None
    ratio = SequenceMatcher(None, left, right).ratio()
    if ratio >= full_string_threshold:
        return round(float(ratio), 4)
    if long.startswith(short + " ") and ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
        return round(float(max(ratio, full_string_threshold)), 4)
    if long.startswith(short) and len(short) >= 4 and ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
        return round(float(max(ratio, full_string_threshold)), 4)
    return None


def _duplicate_score_from_remainders(
    rem_a: str,
    rem_b: str,
    *,
    full_string_threshold: float,
    distinctive_threshold: float,
) -> float | None:
    """Similarity cascade on post-prefix remainders (no short-prefix boost)."""
    if len(rem_a) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN or len(rem_b) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN:
        return None
    if _distinctive_short_token_flip_should_suppress(rem_a, rem_b):
        return None
    prefix_score = _token_prefix_extension_score(
        rem_a,
        rem_b,
        min_short_len=DSI_DUPLICATE_MIN_DISTINCTIVE_LEN,
        full_string_threshold=full_string_threshold,
    )
    if prefix_score is not None:
        return prefix_score
    dist_ratio = SequenceMatcher(None, rem_a, rem_b).ratio()
    if dist_ratio < distinctive_threshold:
        if _leading_distinctive_token_variant(rem_a, rem_b):
            ta = rem_a.split()
            tb = rem_b.split()
            head_a = " ".join(ta[:2])
            head_b = " ".join(tb[:2])
            head_ratio = SequenceMatcher(None, head_a, head_b).ratio()
            if head_ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
                return round(float(head_ratio), 4)
        return None
    full_ratio = SequenceMatcher(None, rem_a, rem_b).ratio()
    if dist_ratio >= DSI_DUPLICATE_DISTINCTIVE_EXACT_CUTOFF:
        if full_ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
            return round(float(full_ratio), 4)
        if rem_a == rem_b:
            combined = max(full_ratio, dist_ratio * 0.95)
            if combined >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
                return round(float(combined), 4)
        return None
    if full_ratio >= full_string_threshold:
        return round(float(full_ratio), 4)
    return None


def dsi_duplicate_similarity_score(
    name_a: str | None,
    name_b: str | None,
    *,
    full_string_threshold: float = DSI_DUPLICATE_FULL_STRING_THRESHOLD,
    distinctive_threshold: float = DSI_DUPLICATE_DISTINCTIVE_THRESHOLD,
) -> float | None:
    """Cascade duplicate score: distinctive stem gate, then full-string similarity.

    Returns ``None`` when the pair must not be flagged (e.g. only generic words match).
  """
    norm_a = normalize_customer_name_for_similarity(name_a)
    norm_b = normalize_customer_name_for_similarity(name_b)
    if len(norm_a) < DSI_DUPLICATE_MIN_NORMALIZED_LEN or len(norm_b) < DSI_DUPLICATE_MIN_NORMALIZED_LEN:
        return None

    lead_a = _leading_distinctive_token(norm_a)
    lead_b = _leading_distinctive_token(norm_b)
    if not lead_a or not lead_b:
        return None
    short_prefix_pair = len(lead_a) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN or len(
        lead_b
    ) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN
    if short_prefix_pair:
        rem_a = _remainder_after_short_leading_prefix(norm_a, lead_a)
        rem_b = _remainder_after_short_leading_prefix(norm_b, lead_b)
        if not rem_a or not rem_b:
            return None
        return _duplicate_score_from_remainders(
            rem_a,
            rem_b,
            full_string_threshold=full_string_threshold,
            distinctive_threshold=distinctive_threshold,
        )

    dist_a, _gen_a = split_distinctive_and_generic_tokens(norm_a)
    dist_b, _gen_b = split_distinctive_and_generic_tokens(norm_b)
    if len(dist_a) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN or len(dist_b) < DSI_DUPLICATE_MIN_DISTINCTIVE_LEN:
        return None

    if _distinctive_short_token_flip_should_suppress(dist_a, dist_b):
        return None

    dist_ratio = SequenceMatcher(None, dist_a, dist_b).ratio()
    if dist_ratio < distinctive_threshold:
        if _leading_distinctive_token_variant(dist_a, dist_b):
            ta = dist_a.split()
            tb = dist_b.split()
            head_a = " ".join(ta[:2])
            head_b = " ".join(tb[:2])
            head_ratio = SequenceMatcher(None, head_a, head_b).ratio()
            if head_ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
                return round(float(head_ratio), 4)
        norm_prefix_score = _token_prefix_extension_score(
            norm_a,
            norm_b,
            min_short_len=DSI_DUPLICATE_MIN_NORMALIZED_LEN,
            full_string_threshold=full_string_threshold,
        )
        if norm_prefix_score is not None:
            return norm_prefix_score
        return None

    full_ratio = SequenceMatcher(None, norm_a, norm_b).ratio()

    if dist_ratio >= DSI_DUPLICATE_DISTINCTIVE_EXACT_CUTOFF:
        if full_ratio >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
            return round(float(full_ratio), 4)
        if dist_a == dist_b:
            combined = max(full_ratio, dist_ratio * 0.95)
            if combined >= DSI_DUPLICATE_FULL_STRING_RELAXED_THRESHOLD:
                return round(float(combined), 4)
        return None

    if full_ratio >= full_string_threshold:
        return round(float(full_ratio), 4)
    return None

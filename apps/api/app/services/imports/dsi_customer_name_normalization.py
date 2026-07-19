"""Customer/dealer display-name normalisation for DSI duplicate detection and matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
        r"\bstate\s+owned\s+company\s+ltd\.?",
        r"\bstate\s+owned\s+company\b",
        r"\bsoc\s+ltd\.?",
        r"\brf\b",
        r"\bnpc\b",
        r"\bcc\b",
        r"\bsoc\b",
    )
)

# Trading-as markers: parenthetical, inline (prefix/mid), and trailing suffix.
_TRADING_AS_PAREN = re.compile(r"\(\s*(?:t/a|a/t|ta:)\s*\)", re.IGNORECASE)
_TRADING_AS_INLINE = re.compile(
    r"\b(?:t/a|a/t|trading\s+as|trading-as|ta:)\s*",
    re.IGNORECASE,
)
_TRADING_AS_SUFFIX = re.compile(r"\s+(?:t/a|a/t)\s*$", re.IGNORECASE)

# Split raw display names into legal + trade parts (before normalize strips T/A).
_TRADING_AS_PAREN_SPLIT = re.compile(
    r"^(?P<legal>.+?)\s*\(\s*(?:t/a|a/t|ta:)\s*\)\s*(?P<trade>.+)$",
    re.IGNORECASE,
)
_TRADING_AS_INLINE_SPLIT = re.compile(
    r"^(?P<legal>.+?)\s+(?:t/a|a/t|trading\s+as|trading-as|ta:)\s+(?P<trade>.+)$",
    re.IGNORECASE,
)


def normalize_customer_name_for_similarity(raw: str | None) -> str:
    """Strip legal suffixes and noise, lowercase, collapse whitespace — for duplicate/compare only.

    Parentheses/dots are removed *before* legal-suffix patterns so forms like
    ``EVETECH (PROPRIETARY) LIMITED`` normalize to ``evetech`` (not ``evetech proprietary``).
    Trading-as markers are stripped first so ``(t/a)`` is not treated as punctuation noise.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    s = _TRADING_AS_PAREN.sub(" ", s)
    s = _TRADING_AS_INLINE.sub(" ", s)
    s = _TRADING_AS_SUFFIX.sub(" ", s)
    # Before legal suffixes: "(PROPRIETARY) LIMITED" → "PROPRIETARY LIMITED"
    s = re.sub(r"[.()]+", " ", s)
    for pat in _LEGAL_SUFFIX_PATTERNS:
        s = pat.sub(" ", s)
    s = re.sub(r"\s*&\s*", " and ", s)
    s = re.sub(r"[,;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_customer_name_token(raw: str | None) -> str:
    """Normalised token stored on candidate context for downstream matching (may be empty)."""
    return normalize_customer_name_for_similarity(raw)


def split_trading_as_raw_parts(raw: str | None) -> tuple[str, str] | None:
    """If ``raw`` has a trading-as marker, return ``(legal_part, trade_part)``; else ``None``."""
    s = (raw or "").strip()
    if not s:
        return None
    m = _TRADING_AS_PAREN_SPLIT.match(s) or _TRADING_AS_INLINE_SPLIT.match(s)
    if m is None:
        return None
    legal = (m.group("legal") or "").strip()
    trade = (m.group("trade") or "").strip()
    if not legal or not trade:
        return None
    return legal, trade


def customer_similarity_lookup_keys(raw: str | None) -> list[str]:
    """Ordered unique sim keys for dim lookup: full normalize, then T/A legal-only, trade-only."""
    keys: list[str] = []
    seen: set[str] = set()

    def _add(key: str) -> None:
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    _add(normalize_customer_name_for_similarity(raw))
    parts = split_trading_as_raw_parts(raw)
    if parts is not None:
        legal, trade = parts
        _add(normalize_customer_name_for_similarity(legal))
        _add(normalize_customer_name_for_similarity(trade))
    return keys


def unique_sim_customer_id(
    sim_name_to_ids: dict[str, list[int]],
    raw: str | None,
) -> tuple[int | None, str | None]:
    """Resolve a unique dim customer via sim keys (full, then T/A legal, then trade).

    Tries keys in order. Returns ``(customer_id, resolution_signal)`` when a key has
    exactly one id. Returns ``(None, None)`` when a tried key is ambiguous (>1) or all miss.
    Does not union hits across keys — preserves the uniqueness gate.
    """
    keys = customer_similarity_lookup_keys(raw)
    if not keys:
        return None, None
    full_key = keys[0]
    parts = split_trading_as_raw_parts(raw)
    legal_key = normalize_customer_name_for_similarity(parts[0]) if parts else ""
    trade_key = normalize_customer_name_for_similarity(parts[1]) if parts else ""

    for key in keys:
        ids = list(dict.fromkeys(sim_name_to_ids.get(key, [])))
        if len(ids) > 1:
            return None, None
        if len(ids) == 1:
            if key == full_key:
                signal = "similar_customer_name"
            elif key == legal_key:
                signal = "similar_customer_name_trading_as_legal"
            elif key == trade_key:
                signal = "similar_customer_name_trading_as_trade"
            else:
                signal = "similar_customer_name"
            return int(ids[0]), signal
    return None, None


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
        "computers",
        "computer",
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

# Dealer-group duplicate scoring (root identity).
DSI_DUPLICATE_FULL_STRING_THRESHOLD: float = 0.88
DSI_DUPLICATE_MIN_NORMALIZED_LEN: int = 4
DSI_DUPLICATE_MIN_DISTINCTIVE_LEN: int = 3
DSI_ROOT_FUZZY_RATIO_THRESHOLD: float = 0.92
DSI_ROOT_MIN_TOKEN_LEN: int = 2

# Right-peel only — never includes ``trading`` (part of registered name when present).
_ROOT_DESCRIPTOR_TAIL_TOKENS: frozenset[str] = frozenset(
    {
        "services",
        "service",
        "solutions",
        "solution",
        "technologies",
        "technology",
        "tech",
        "computers",
        "computer",
        "systems",
        "system",
        "electronics",
        "electronic",
        "holdings",
        "holding",
        "group",
        "international",
        "global",
        "distribution",
        "distributor",
        "distributors",
        "enterprises",
        "enterprise",
        "industries",
        "industry",
        "wholesale",
        "retail",
        "logistics",
        "supply",
        "supplies",
        "home",
        "connect",
        "connection",
        "support",
        "world",
        "direct",
        "big",
    }
)

# Two-character product-line tails when a longer head token precedes them.
_ROOT_SHORT_DESCRIPTOR_TAILS: frozenset[str] = frozenset({"sp"})

_COMPUTER_TAIL_FAMILY: frozenset[str] = frozenset({"computer", "computers"})

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


def _collapse_spaced_acronym_tokens(normalized: str) -> str:
    """Join runs of single-letter tokens (``b c s`` → ``bcs``) for acronym-style dealer names."""
    tokens = (normalized or "").split()
    if not tokens:
        return ""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if len(t) == 1 and t.isalpha():
            buf = [t]
            j = i + 1
            while j < len(tokens) and len(tokens[j]) == 1 and tokens[j].isalpha():
                buf.append(tokens[j])
                j += 1
            out.append("".join(buf) if len(buf) >= 2 else t)
            i = j
        else:
            out.append(t)
            i += 1
    return " ".join(out)


def _normalize_for_duplicate_compare(raw: str | None) -> str:
    return _collapse_spaced_acronym_tokens(normalize_customer_name_for_similarity(raw))


def _root_lead_token(root: str) -> str:
    tokens = (root or "").split()
    return tokens[0] if tokens else ""


def _is_descriptor_tail_token(token: str, *, tokens_before: int) -> bool:
    if token in _ROOT_DESCRIPTOR_TAIL_TOKENS:
        return True
    if token in _ROOT_SHORT_DESCRIPTOR_TAILS and tokens_before >= 1:
        return True
    return False


def _peel_trading_alias_tail(tokens: list[str]) -> list[str]:
    """Remove one trailing alias word after t/a normalization (e.g. counterparty name), not core identity."""
    if len(tokens) < 3:
        return tokens
    last = tokens[-1]
    if _is_descriptor_tail_token(last, tokens_before=len(tokens) - 1):
        return tokens
    prior = tokens[-2]
    # Require a substantial preceding token so short initials + company name (e.g. ``b and a computronics``) are kept.
    if len(prior) < 8 and prior not in _ROOT_DESCRIPTOR_TAIL_TOKENS:
        return tokens
    if len(last) >= 4 and last.isalpha():
        return tokens[:-1]
    return tokens


def extract_root_identity(normalized: str) -> str:
    """Extract core business root from a normalized name (right-peel descriptors only)."""
    tokens = [t for t in (normalized or "").split() if t]
    if not tokens:
        return ""
    tokens = _peel_trading_alias_tail(tokens)
    while len(tokens) > 1:
        if _is_descriptor_tail_token(tokens[-1], tokens_before=len(tokens) - 1):
            tokens.pop()
        else:
            break
    if not tokens:
        return ""
    return " ".join(tokens)


def extract_root_identity_from_raw(raw: str | None) -> str:
    return extract_root_identity(_normalize_for_duplicate_compare(raw))


def _tails_compatible(tail_a: list[str], tail_b: list[str]) -> bool:
    if tail_a == tail_b:
        return True
    if tail_a and tail_b and all(t in _COMPUTER_TAIL_FAMILY for t in tail_a) and all(t in _COMPUTER_TAIL_FAMILY for t in tail_b):
        return True
    joined_a = " ".join(tail_a)
    joined_b = " ".join(tail_b)
    if not joined_a or not joined_b:
        return False
    return SequenceMatcher(None, joined_a, joined_b).ratio() >= 0.85


def _short_lead_same_root_different_line(norm_a: str, norm_b: str, root_a: str, root_b: str) -> bool:
    """Block TB Computers vs TB Solutions style matches when roots collapse to the same short token."""
    if root_a != root_b:
        return False
    lead = _root_lead_token(root_a)
    if len(lead) > DSI_DUPLICATE_MIN_DISTINCTIVE_LEN:
        return False
    if norm_a == norm_b:
        return False
    tokens_a = norm_a.split()
    tokens_b = norm_b.split()
    tail_a = tokens_a[1:]
    tail_b = tokens_b[1:]
    if not tail_a or not tail_b:
        return False
    if _tails_compatible(tail_a, tail_b):
        return False
    return True


def _root_it_its_variant(root_a: str, root_b: str) -> bool:
    ta = root_a.split()
    tb = root_b.split()
    if len(ta) < 2 or len(tb) < 2 or ta[0] != tb[0]:
        return False
    if not _one_edit_apart(ta[1], tb[1]):
        return False
    return abs(len(ta[1]) - len(tb[1])) <= 1 and min(len(ta[1]), len(tb[1])) >= 2


def compare_root_identities(root_a: str, root_b: str, *, norm_a: str = "", norm_b: str = "") -> float | None:
    """Return similarity score when roots match (exact or fuzzy); ``None`` when not duplicates."""
    ra = (root_a or "").strip()
    rb = (root_b or "").strip()
    if not ra or not rb:
        return None
    if len(ra) < DSI_ROOT_MIN_TOKEN_LEN or len(rb) < DSI_ROOT_MIN_TOKEN_LEN:
        return None

    lead_a = _root_lead_token(ra)
    lead_b = _root_lead_token(rb)
    if not lead_a or not lead_b:
        return None
    if (
        len(lead_a) <= DSI_DUPLICATE_MIN_DISTINCTIVE_LEN
        and len(lead_b) <= DSI_DUPLICATE_MIN_DISTINCTIVE_LEN
        and lead_a != lead_b
    ):
        return None

    if norm_a and norm_b and _short_lead_same_root_different_line(norm_a, norm_b, ra, rb):
        return None

    if _distinctive_short_token_flip_should_suppress(ra, rb):
        return None

    if ra == rb:
        return 1.0

    if len(lead_a) <= DSI_DUPLICATE_MIN_DISTINCTIVE_LEN or len(lead_b) <= DSI_DUPLICATE_MIN_DISTINCTIVE_LEN:
        return None

    ratio = SequenceMatcher(None, ra, rb).ratio()
    if _root_it_its_variant(ra, rb):
        return round(max(DSI_DUPLICATE_FULL_STRING_THRESHOLD, ratio), 4)

    if ratio < DSI_ROOT_FUZZY_RATIO_THRESHOLD:
        return None

    return round(max(DSI_DUPLICATE_FULL_STRING_THRESHOLD, ratio), 4)


def compare_root_identities_from_raw(name_a: str | None, name_b: str | None) -> float | None:
    norm_a = _normalize_for_duplicate_compare(name_a)
    norm_b = _normalize_for_duplicate_compare(name_b)
    if not norm_a or not norm_b:
        return None
    if norm_a == norm_b:
        return 1.0
    return compare_root_identities(
        extract_root_identity(norm_a),
        extract_root_identity(norm_b),
        norm_a=norm_a,
        norm_b=norm_b,
    )


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


def _distinctive_stem_is_short_only(distinctive: str) -> bool:
    """True when every distinctive token is at most 3 characters (e.g. stem ``tb`` only)."""
    tokens = [t for t in (distinctive or "").split() if t]
    return bool(tokens) and all(len(t) <= DSI_DUPLICATE_MIN_DISTINCTIVE_LEN for t in tokens)


@dataclass(frozen=True)
class DealerGroupDuplicateEvaluation:
    score: float
    match_basis: str  # dealer_group_exact | dealer_group_similar | dealer_group_prefix_stem | ...


def evaluate_company_stem_duplicate(
    name_a: str | None,
    name_b: str | None,
) -> DealerGroupDuplicateEvaluation | None:
    """Retired — prefix-stem path removed; roots must match via ``evaluate_dealer_group_duplicate``."""
    return None


def evaluate_dealer_group_duplicate(
    name_a: str | None,
    name_b: str | None,
    *,
    full_string_threshold: float = DSI_DUPLICATE_FULL_STRING_THRESHOLD,
    distinctive_threshold: float | None = None,
) -> DealerGroupDuplicateEvaluation | None:
    """Score dealer-group display names using root identity comparison."""
    del distinctive_threshold, full_string_threshold
    norm_a = _normalize_for_duplicate_compare(name_a)
    norm_b = _normalize_for_duplicate_compare(name_b)
    if not norm_a or not norm_b:
        return None
    if len(norm_a) < DSI_DUPLICATE_MIN_NORMALIZED_LEN or len(norm_b) < DSI_DUPLICATE_MIN_NORMALIZED_LEN:
        return None
    root_a = extract_root_identity(norm_a)
    root_b = extract_root_identity(norm_b)
    score = compare_root_identities(root_a, root_b, norm_a=norm_a, norm_b=norm_b)
    if score is None:
        return None
    if root_a == root_b:
        basis = "dealer_group_exact"
    else:
        basis = "dealer_group_similar"
    return DealerGroupDuplicateEvaluation(score=score, match_basis=basis)


def dsi_duplicate_similarity_score(
    name_a: str | None,
    name_b: str | None,
    *,
    full_string_threshold: float = DSI_DUPLICATE_FULL_STRING_THRESHOLD,
    distinctive_threshold: float | None = None,
) -> float | None:
    """Root-identity duplicate score for dealer-group and source-customer name pairs."""
    del full_string_threshold, distinctive_threshold
    return compare_root_identities_from_raw(name_a, name_b)

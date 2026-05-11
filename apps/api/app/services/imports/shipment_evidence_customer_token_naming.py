"""Three-layer customer token → suggested display name (shipment evidence steward).

Layer 1: statistical leading-prefix detection per import job (distinct tokens), including
**prefix families** inferred from structural similarity so variants like Q1–Q4 jointly meet
coverage thresholds.
Layer 2: optional ``SourceDefinition.expected_template["shipment_customer_token"]`` strip rules.
Layer 3: title-case fallback with whitespace normalisation (never empty).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import ceil
from typing import Any

from app.services.imports.shipment_evidence_candidate_names import _soft_title


def _norm_key(s: str | None) -> str:
    """Match ``distributor_sales_inventory._norm_key`` without importing that module."""
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


# --- Layer 1 defaults (constants block; not inline magic numbers) ---
MIN_COVERAGE_PCT: float = 0.15
MIN_ABSOLUTE_COUNT: int = 3
MAX_PREFIX_SCAN_LEN: int = 64

# After stripping a detected prefix, remainder must be at least this long or we keep the original token.
MIN_REMAINDER_LEN: int = 3

# Normalised remainder matching any of these → special_category ``noise_only`` (not a customer name).
NOISE_ONLY_WORDS: frozenset[str] = frozenset(
    {
        "sample",
        "open channel",
        "channel",
        "retail",
        "accessory",
        "accy",
    }
)

# If normalised suggested vs original similarity is below this, flag steward review (difflib ratio).
NEEDS_NAME_REVIEW_RATIO_THRESHOLD: float = 0.55

_SEP_RUN = re.compile(r"[\s\-–—:]+")
# Strip PO / Alviva-style reference tails (must NOT match the substring "po" inside words like "Pool").
_RE_CUSTOMER_REF_TAIL = re.compile(
    r"(?:/|\s+po:\s*|\bpo\d|\bpo\s+[A-Z0-9]{2,}).*$",
    re.IGNORECASE,
)
# Trailing fiscal quarter token after the customer name (e.g. "Compuspeed Q1").
_RE_TRAILING_QUARTER_TOKEN = re.compile(r"(?i)\s+Q[1-4]$")


def _norm_sep(s: str) -> str:
    """Lowercase, unify dash variants to ASCII hyphen, collapse whitespace (prefix matching only)."""
    t = (s or "").strip().lower()
    for ch in "–—":
        t = t.replace(ch, "-")
    t = re.sub(r"\s+", " ", t)
    return t


def _lead_zone(raw: str) -> str:
    """Leading segment before first separator (space, dash variants, colon)."""
    s = (raw or "").strip()
    if not s:
        return ""
    m = _SEP_RUN.search(s)
    if m:
        return s[: m.start()]
    return s


def _boundary_ok(full_norm: str, pref_norm: str) -> bool:
    if not full_norm.startswith(pref_norm):
        return False
    if len(full_norm) <= len(pref_norm):
        return True
    nxt = full_norm[len(pref_norm) : len(pref_norm) + 1]
    return nxt in (" ", "-", ":", "")


def _collect_prefix_candidates(distinct_tokens: list[str]) -> list[str]:
    """All length>=2 leading substrings of each token's lead zone (deduped by normalised form)."""
    seen: set[str] = set()
    out: list[str] = []
    for tok in distinct_tokens:
        zone = _lead_zone(tok)
        if len(zone) < 2:
            continue
        lim = min(len(zone), MAX_PREFIX_SCAN_LEN)
        for k in range(2, lim + 1):
            p = zone[:k]
            pn = _norm_sep(p)
            if len(pn) < 2:
                continue
            if pn not in seen:
                seen.add(pn)
                out.append(p)
    return out


def _hits_for_prefix(distinct_tokens: list[str], pref: str) -> set[str]:
    pn = _norm_sep(pref)
    if len(pn) < 2:
        return set()
    return {t for t in distinct_tokens if _boundary_ok(_norm_sep(t), pn)}


def _digit_family_signature(pref: str) -> str | None:
    """Structural signature where digit runs are collapsed (Q1/Q2 → same family)."""
    pn = _norm_sep(pref)
    if not re.search(r"\d", pn):
        return None
    return re.sub(r"\d+", "#", pn)


class _PrefixUF:
    __slots__ = ("parent",)

    def __init__(self, items: list[str]) -> None:
        self.parent: dict[str, str] = {x: x for x in items}

    def find(self, x: str) -> str:
        p = self.parent
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _union_suffix_related_letter_prefixes(candidates: list[str], uf: _PrefixUF) -> None:
    """Merge letter-only prefixes when one normalised form is a suffix of the other (generic TB/FWTB style)."""
    letter_ps = [p for p in candidates if _digit_family_signature(p) is None and len(_norm_sep(p)) >= 2]
    pn_map = {p: _norm_sep(p) for p in letter_ps}
    for i, p in enumerate(letter_ps):
        a = pn_map[p]
        if len(a) < 2:
            continue
        for q in letter_ps[i + 1 :]:
            b = pn_map[q]
            if len(b) < 2:
                continue
            if a.endswith(b) or b.endswith(a):
                if abs(len(a) - len(b)) <= 8:
                    uf.union(p, q)


def _union_condensed_letter_prefixes(candidates: list[str], uf: _PrefixUF) -> None:
    """Merge prefixes whose letters match when spaces are removed (``FW TB`` ↔ ``TB``)."""
    letter_ps = [p for p in candidates if _digit_family_signature(p) is None and len(_norm_sep(p)) >= 2]
    condensed = {p: re.sub(r"\s+", "", _norm_sep(p)) for p in letter_ps}
    for i, p in enumerate(letter_ps):
        a = condensed[p]
        if len(a) < 2:
            continue
        for q in letter_ps[i + 1 :]:
            b = condensed[q]
            if len(b) < 2:
                continue
            if a.endswith(b) or b.endswith(a):
                if abs(len(a) - len(b)) <= 8:
                    uf.union(p, q)


def _region_channel_prefix_variants(raw: str) -> list[str]:
    """Region / channel leading segments (``SADC -``, ``TB -``, ``FW TB`` …) as extra prefix candidates."""
    t = raw.strip()
    out: list[str] = []
    if re.match(r"(?i)^fw\s+tb\b", t):
        m = re.match(r"(?i)^(fw\s+tb)(\s+[\-–—]\s*|\s+)", t)
        if m:
            out.append(t[: m.end()].rstrip())
    m = re.match(r"(?i)^(sadc)(\s+[\-–—]\s*)", t)
    if m:
        out.append(t[: m.end()].rstrip())
    m = re.match(r"(?i)^(tb)(\s+[\-–—]\s*)", t)
    if m:
        out.append(t[: m.end()].rstrip())
    return out


def _extend_candidates_with_region_prefixes(distinct_tokens: list[str], candidates: list[str]) -> None:
    seen = {_norm_sep(p) for p in candidates}
    for raw in distinct_tokens:
        for pref in _region_channel_prefix_variants(raw):
            pn = _norm_sep(pref)
            if len(pn) >= 2 and pn not in seen:
                seen.add(pn)
                candidates.append(pref)


def detect_statistical_prefixes(distinct_tokens: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Return (prefixes longest-first for stripping, audit dict for job context).

    Individual prefixes must hit ``min_need`` distinct tokens **or** belong to a **prefix family**
    whose **union** of distinct-token hits meets the same thresholds. Families are inferred:
    digit-bearing prefixes share a digit-collapsed signature; letter-only prefixes may merge on
    normalised suffix containment (e.g. one zone prefix ending with another).
    """
    toks = sorted({t.strip() for t in distinct_tokens if t and str(t).strip()})
    n = len(toks)
    if n == 0:
        return [], {"distinct_token_count": 0, "candidates": [], "prefix_families": []}

    min_need = max(MIN_ABSOLUTE_COUNT, int(ceil(MIN_COVERAGE_PCT * n)))
    candidates = _collect_prefix_candidates(toks)
    _extend_candidates_with_region_prefixes(toks, candidates)
    hits: dict[str, set[str]] = {p: _hits_for_prefix(toks, p) for p in candidates}

    uf = _PrefixUF(candidates)
    sig_buckets: dict[str, list[str]] = defaultdict(list)
    for p in candidates:
        sig = _digit_family_signature(p)
        if sig is not None:
            sig_buckets[sig].append(p)
    for members in sig_buckets.values():
        if len(members) < 2:
            continue
        head = members[0]
        for m in members[1:]:
            uf.union(head, m)
    _union_suffix_related_letter_prefixes(candidates, uf)
    _union_condensed_letter_prefixes(candidates, uf)

    clusters: dict[str, set[str]] = defaultdict(set)
    for p in candidates:
        clusters[uf.find(p)].add(p)

    selected: set[str] = set()
    families_audit: list[dict[str, Any]] = []
    for _root, members in clusters.items():
        union_hits: set[str] = set()
        for m in members:
            union_hits |= hits.get(m, set())
        ucount = len(union_hits)
        ok_family = ucount >= min_need and ucount / n >= MIN_COVERAGE_PCT
        if ok_family:
            selected.update(members)
            families_audit.append(
                {
                    "members": sorted(members, key=lambda x: (-len(x), x)),
                    "distinct_token_hits": ucount,
                    "min_required": min_need,
                    "distinct_token_count": n,
                }
            )

    for p, hs in hits.items():
        if len(hs) >= min_need:
            selected.add(p)

    picked = sorted(selected, key=lambda x: len(x), reverse=True)
    audit_candidates = [
        {
            "prefix": p,
            "normalized_prefix": _norm_sep(p),
            "distinct_token_hits": len(hits.get(p, set())),
            "min_required": min_need,
            "distinct_token_count": n,
        }
        for p in picked
    ]
    meta: dict[str, Any] = {
        "distinct_token_count": n,
        "min_coverage_pct": MIN_COVERAGE_PCT,
        "min_absolute_count": MIN_ABSOLUTE_COUNT,
        "computed_min_required": min_need,
        "candidates": audit_candidates,
        "prefix_families": families_audit,
    }
    return picked, meta


def _apply_detected_prefixes(raw: str, prefixes_longest_first: list[str]) -> tuple[str, tuple[str, ...]]:
    """Apply longest-first detected prefixes; return (possibly unchanged string, tuple applied)."""
    s = (raw or "").strip()
    if not s:
        return "", ()
    applied: list[str] = []
    work = s
    for pref in prefixes_longest_first:
        p = pref.strip()
        if len(p) < 2:
            continue
        if work.lower().startswith(p.lower()):
            rest = work[len(p) :].lstrip(" \t")
            rest = re.sub(r"^[\-–—:]+", "", rest).lstrip(" \t")
            if len(_norm_sep(rest)) >= MIN_REMAINDER_LEN:
                work = rest
                applied.append(p)
    return work, tuple(applied)


def _layer2_source_strips(source_def: Any) -> list[str]:
    """Explicit leading prefixes from SourceDefinition.expected_template (longest first)."""
    if source_def is None:
        return []
    et = getattr(source_def, "expected_template", None)
    if not isinstance(et, dict):
        return []
    block = et.get("shipment_customer_token")
    if not isinstance(block, dict):
        return []
    raw = block.get("strip_leading_prefixes")
    if not isinstance(raw, list):
        return []
    out = [str(x).strip() for x in raw if isinstance(x, str) and len(str(x).strip()) >= 2]
    return sorted(set(out), key=len, reverse=True)


def _apply_layer2_sequence(after_l1: str, l2_prefs: list[str]) -> tuple[str, tuple[str, ...]]:
    work = (after_l1 or "").strip()
    applied: list[str] = []
    for pref in l2_prefs:
        if len(pref) < 2:
            continue
        if work.lower().startswith(pref.lower()):
            rest = work[len(pref) :].lstrip(" \t")
            rest = re.sub(r"^[\-–—:]+", "", rest).lstrip(" \t")
            if len(_norm_sep(rest)) >= MIN_REMAINDER_LEN:
                work = rest
                applied.append(pref)
    return work, tuple(applied)


def _strip_customer_reference_annotation(s: str) -> str:
    """Remove trailing PO / order references so partner tokens can group (e.g. eShop + PO lines)."""
    t = (s or "").strip()
    if not t:
        return ""
    m = _RE_CUSTOMER_REF_TAIL.search(t)
    if m:
        t = t[: m.start()].strip()
    return t


def _strip_trailing_quarter_qualifier(s: str) -> str:
    """Remove a trailing ``Q1``–``Q4`` token (region / channel reporting bucket), not part of the legal name."""
    t = (s or "").strip()
    if not t:
        return ""
    m = _RE_TRAILING_QUARTER_TOKEN.search(t)
    if m:
        t = t[: m.start()].strip()
    return t


def _internal_note_after_comma(merged: str) -> tuple[str | None, bool]:
    """If remainder has `,` and >3 words after the comma, treat as internal note (left segment is the name)."""
    if "," not in merged:
        return None, False
    left, right = merged.split(",", 1)
    wc = len([w for w in right.split() if w.strip()])
    if wc > 3:
        return left.strip(), True
    return None, False


# Last-token trailing ``s`` removed only for clear plural shapes (never consonant-before-``s`` alone).
_EXTRA_TRAILING_S_PLURAL = frozenset({"afrocentrics"})
_NO_TRAILING_S_PLURAL = frozenset({"charles", "myles", "mauritius", "stylus", "debris"})


def _should_singularize_trailing_s_last_word(low_last: str) -> bool:
    w = low_last.lower()
    if len(w) < 5 or not w.endswith("s") or w.endswith("ss"):
        return False
    if w in _EXTRA_TRAILING_S_PLURAL:
        return True
    if w in _NO_TRAILING_S_PLURAL:
        return False
    for suf in ("ious", "eous", "uous", "ius", "sis", "ness", "less", "lands", "ous"):
        if w.endswith(suf):
            return False
    # ``stylus``, ``cactus``: consonant + ``us`` at word end (not ``…ous``).
    if re.search(r"[^aeiouy]us$", w):
        return False
    # ``schools`` (``…ools``), ``girls`` (``…irls``); exclude ``…rles`` (``Charles``).
    if re.search(r"[aeiou]{2,}ls$", w) or re.search(r"[aeiou][bcdfghjkmnpqrtvwxz]ls$", w):
        return not w.endswith("rles")
    prev = w[-2]
    if prev not in "aeiouy":
        return False
    return True


def _singularize_last_word_display(s: str) -> tuple[str, bool]:
    """If last word is a productive English plural ``…Xs`` (``X`` vowel or ``…irls`` / ``…ools``), singularise."""
    parts = (s or "").strip().split()
    if not parts:
        return s, False
    last = parts[-1]
    if not _should_singularize_trailing_s_last_word(last):
        return s, False
    stem = last[:-1]
    if len(stem) < 4:
        return s, False
    parts[-1] = stem
    return " ".join(parts), True


def plural_merge_canonical_display(s: str) -> str:
    """Canonical display for plural/singular merge (singular when trailing `s` rule applies)."""
    out, _ = _singularize_last_word_display(s)
    return out


def _tokenize_suggested(s: str) -> list[str]:
    return [w for w in _norm_key(s).split(" ") if w]


def _aligned_prefix_tokens_short_vs_long(short: list[str], long: list[str]) -> bool:
    """Each short token is a prefix of the aligned long token (same index); at most one extra long token."""
    if len(short) > len(long):
        short, long = long, short
    if not short:
        return False
    for i, sw in enumerate(short):
        if i >= len(long):
            return False
        lw = long[i]
        if not lw.startswith(sw) and not sw.startswith(lw):
            return False
    extra = len(long) - len(short)
    return extra <= 1


_DUP_STRIP_GENERIC_WORDS: frozenset[str] = frozenset(
    {
        "furniture",
        "school",
        "development",
        "education",
        "health",
        "college",
        "university",
        "primary",
        "secondary",
        "warehouse",
        "group",
        "solutions",
    }
)


def _strip_generic_words_for_duplicate_compare(s: str) -> str:
    """Remove common generic tokens before duplicate similarity (reduces false positives)."""
    t = re.sub(r"\s+", " ", (s or "").strip().lower())
    parts = [w for w in t.split() if w and w not in _DUP_STRIP_GENERIC_WORDS]
    return " ".join(parts)


def adjacent_transpose_typo_duplicate_hint(a: str, b: str) -> bool:
    """True if two names differ only by swapping one adjacent character (e.g. Marko / Makro)."""
    la = re.sub(r"\s+", " ", (a or "").strip().lower())
    lb = re.sub(r"\s+", " ", (b or "").strip().lower())
    if len(la) != len(lb) or len(la) < 5:
        return False
    if la == lb:
        return False
    for i in range(len(la) - 1):
        swapped = la[:i] + la[i + 1] + la[i] + la[i + 2 :]
        if swapped == lb:
            return True
    return False


def suggested_names_similar_for_duplicate_flag(a: str, b: str) -> bool:
    """Heuristic for steward duplicate hints (not auto-merge)."""
    a = _strip_generic_words_for_duplicate_compare(a)
    b = _strip_generic_words_for_duplicate_compare(b)
    if not a or not b:
        return False
    ta, tb = _tokenize_suggested(a), _tokenize_suggested(b)
    if not ta or not tb:
        return False
    if ta[0] != tb[0]:
        return False
    if SequenceMatcher(None, _norm_key(a), _norm_key(b)).ratio() >= 0.82:
        return True
    if len(ta) <= len(tb):
        return _aligned_prefix_tokens_short_vs_long(ta, tb)
    return _aligned_prefix_tokens_short_vs_long(tb, ta)


def annotate_shipment_customer_pending_duplicates(pending: dict[str, Any]) -> None:
    """Set ``possible_duplicate_of`` / ``typo_suspected_of`` on customer pending buckets (pre-DB)."""
    items = list(pending.items())
    for i, (nk_a, pa) in enumerate(items):
        sa = (pa.get("display_suggested_name") or "").strip()
        if not sa or pa.get("special_category") in ("noise_only", "internal_note"):
            continue
        if len(_norm_key(sa)) < 8:
            continue
        for nk_b, pb in items[i + 1 :]:
            sb = (pb.get("display_suggested_name") or "").strip()
            if not sb or pb.get("special_category") in ("noise_only", "internal_note"):
                continue
            if len(_norm_key(sb)) < 8:
                continue
            if suggested_names_similar_for_duplicate_flag(sa, sb):
                pa.setdefault("possible_duplicate_of", []).append(nk_b)
                pb.setdefault("possible_duplicate_of", []).append(nk_a)
            elif adjacent_transpose_typo_duplicate_hint(sa, sb):
                pa.setdefault("possible_duplicate_of", []).append(nk_b)
                pb.setdefault("possible_duplicate_of", []).append(nk_a)
                pa.setdefault("typo_suspected_of", []).append(nk_b)
                pb.setdefault("typo_suspected_of", []).append(nk_a)
    for pb in pending.values():
        raw = pb.get("possible_duplicate_of")
        if isinstance(raw, list) and raw:
            pb["possible_duplicate_of"] = sorted({str(x) for x in raw if str(x).strip()})[:32]
        raw_t = pb.get("typo_suspected_of")
        if isinstance(raw_t, list) and raw_t:
            pb["typo_suspected_of"] = sorted({str(x) for x in raw_t if str(x).strip()})[:32]
        elif "typo_suspected_of" in pb:
            pb.pop("typo_suspected_of", None)


@dataclass(frozen=True)
class CustomerTokenNamingResult:
    suggested_name: str
    special_category: str | None  # e.g. "noise_only", "internal_note"
    needs_name_review: bool
    layer1_prefixes_applied: tuple[str, ...]
    layer2_prefixes_applied: tuple[str, ...]


def suggest_customer_token_name(
    raw: str,
    *,
    statistical_prefixes_longest_first: list[str],
    source_def: Any,
) -> CustomerTokenNamingResult:
    """Run Layer 1 → 2 → 3 for a single raw token."""
    original = (raw or "").strip()
    if not original:
        return CustomerTokenNamingResult(
            suggested_name="",
            special_category=None,
            needs_name_review=False,
            layer1_prefixes_applied=(),
            layer2_prefixes_applied=(),
        )

    after_l1, l1_applied = _apply_detected_prefixes(original, statistical_prefixes_longest_first)
    l2_prefs = _layer2_source_strips(source_def)
    after_l2, l2_applied = _apply_layer2_sequence(after_l1, l2_prefs)

    merged = re.sub(r"\s+", " ", after_l2.strip())
    if not merged:
        merged = original

    merged = _strip_customer_reference_annotation(merged)
    merged = _strip_trailing_quarter_qualifier(merged)
    merged = re.sub(r"\s+", " ", merged.strip())
    if not merged:
        merged = original

    note_left, is_note = _internal_note_after_comma(merged)
    if is_note and note_left:
        disp = _soft_title(note_left)[:256] or note_left[:256]
        return CustomerTokenNamingResult(
            suggested_name=disp,
            special_category="internal_note",
            needs_name_review=True,
            layer1_prefixes_applied=l1_applied,
            layer2_prefixes_applied=l2_applied,
        )

    rem_norm = _norm_sep(merged)
    if rem_norm in NOISE_ONLY_WORDS:
        disp = _soft_title(original)[:256] or original[:256]
        return CustomerTokenNamingResult(
            suggested_name=disp,
            special_category="noise_only",
            needs_name_review=True,
            layer1_prefixes_applied=l1_applied,
            layer2_prefixes_applied=l2_applied,
        )

    sug = _soft_title(merged)[:256]
    if not sug.strip():
        sug = original[:256]

    orig_n = _norm_sep(original)
    sug_n = _norm_sep(sug)
    needs = False
    if orig_n and sug_n:
        ratio = SequenceMatcher(None, orig_n, sug_n).ratio()
        olen, slen = len(orig_n), len(sug_n)
        len_ratio = min(olen, slen) / max(olen, slen, 1)
        if ratio < NEEDS_NAME_REVIEW_RATIO_THRESHOLD or len_ratio < 0.55:
            needs = True

    return CustomerTokenNamingResult(
        suggested_name=sug,
        special_category=None,
        needs_name_review=needs,
        layer1_prefixes_applied=l1_applied,
        layer2_prefixes_applied=l2_applied,
    )


def grouped_candidate_normalized_key(
    *,
    suggested_name: str,
    source_tokens: list[str],
    special_category: str | None,
) -> str:
    """Stable ``normalized_key`` for ``ImportEntityMappingCandidate`` (unique per job+entity).

    For normal (non-noise) rows the key is **only** derived from the post–Layer-1/2/3
    ``suggested_name`` (collapsed whitespace, lowercased via ``_norm_key``). Raw
    ``source_tokens`` are not used for that path so a shared prefix in source text
    cannot leak into ``normalized_key``.

    ``noise_only`` / ``internal_note`` rows use deterministic hashes of the grouped raw token set.
    """
    if special_category == "noise_only":
        blob = "|".join(sorted({t.strip() for t in source_tokens if t.strip()}))
        h = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:48]
        return f"sc:{h}"[:512]
    if special_category == "internal_note":
        blob = "|".join(sorted({t.strip() for t in source_tokens if t.strip()}))
        h = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:48]
        return f"in:{h}"[:512]
    clean = (suggested_name or "").strip()
    nk = _norm_key(clean)
    if nk:
        return nk[:512]
    blob = "|".join(sorted({t.strip() for t in source_tokens if t.strip()}))
    h = hashlib.sha256((clean + "\n" + blob).encode("utf-8")).hexdigest()[:48]
    return f"blank:{h}"[:512]

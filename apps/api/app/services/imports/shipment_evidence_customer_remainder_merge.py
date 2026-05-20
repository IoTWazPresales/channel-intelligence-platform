"""Intra-job customer pending-map passes (segment-based merge + Open Channel consolidation).

Mutates the pending candidate map **after** plural merge and duplicate annotation in
``shipment_evidence_import``. Does not change statistical prefix / plural / Q-strip naming
pipelines in ``shipment_evidence_customer_token_naming``.

1) **Segment merge:** dash-split + per-segment cleaning, fuzzy-match to other candidates' full names.
2) **Open Channel consolidation:** merge rows matching ``open channel`` phrase, cleaned ``channel``,
   or distributor-name collision (see ``_open_channel_consolidation_hit``), into one ``Open Channel``
   provisional-ready row (``special_category`` cleared).
"""

from __future__ import annotations

import re
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from app.services.imports.shipment_evidence_customer_token_naming import grouped_candidate_normalized_key

_RATIO_MERGE: float = 0.88
_RATIO_HINT_LO: float = 0.70

# Whole-segment noise (case-insensitive exact match after trim).
_WHOLE_SEGMENT_NOISE: frozenset[str] = frozenset(
    {"sadc", "fw", "tb", "emea", "apac", "latam", "eu", "retail", "q1", "q2", "q3", "q4"}
)

_RE_FW_TB_PHRASE = re.compile(r"(?i)\bfw\s+tb\b")
_RE_Q_LEAD_TRAIL = re.compile(r"(?i)(^\s*Q\d+\s*|\s+Q\d+\s*$)")


def _norm_hyphens(s: str) -> str:
    t = (s or "").strip()
    for ch in "–—":
        t = t.replace(ch, "-")
    return t


def _ratio(a: str, b: str) -> float:
    la = (a or "").strip().lower()
    lb = (b or "").strip().lower()
    if not la or not lb:
        return 0.0
    return SequenceMatcher(None, la, lb).ratio()


def _strip_q_tokens_segment(seg: str) -> str:
    t = (seg or "").strip()
    if not t:
        return ""
    prev = None
    while prev != t:
        prev = t
        t = _RE_Q_LEAD_TRAIL.sub(" ", t).strip()
    return t


def _strip_noise_words_segment(seg: str) -> str:
    t = _norm_hyphens(_RE_FW_TB_PHRASE.sub(" ", seg))
    t = re.sub(r"\s+", " ", t).strip()
    if t.lower() in _WHOLE_SEGMENT_NOISE:
        return ""
    return t


def _clean_segment(seg: str) -> str:
    t = _strip_q_tokens_segment(seg)
    t = _strip_noise_words_segment(t)
    return re.sub(r"\s+", " ", t).strip()


def _segments_from_display(display: str) -> list[str]:
    raw = _norm_hyphens(display)
    if not raw:
        return []
    return [p for p in raw.split("-")]


def _usable_cleaned_segments(display: str) -> list[str]:
    out: list[str] = []
    for part in _segments_from_display(display):
        c = _clean_segment(part)
        if len(c) >= 3:
            out.append(c)
    return out


def _build_targets(
    pending: dict[str, dict[str, Any]], *, exclude_nk: str | None = None
) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for nk, pb in pending.items():
        if exclude_nk is not None and nk == exclude_nk:
            continue
        if pb.get("special_category") in ("noise_only", "internal_note"):
            continue
        disp = (pb.get("display_suggested_name") or "").strip()
        if not disp:
            continue
        rows.append((nk, disp, pb))
    return sorted(rows, key=lambda x: x[0])


def _targets_at_or_above(
    segments: list[str], targets: list[tuple[str, str, dict[str, Any]]], *, floor: float
) -> dict[str, float]:
    """Map target nk -> max ratio across all segments."""
    best_by: dict[str, float] = {}
    for seg in segments:
        for nk, disp, _pb in targets:
            r = _ratio(seg, disp)
            prev = best_by.get(nk, 0.0)
            if r > prev:
                best_by[nk] = r
    return {nk: r for nk, r in best_by.items() if r >= floor}


def _dedupe_dup_list(pb: dict[str, Any]) -> None:
    raw = pb.get("possible_duplicate_of")
    if not isinstance(raw, list) or not raw:
        pb.pop("possible_duplicate_of", None)
        return
    dedup = sorted({str(x).strip() for x in raw if str(x).strip()})[:32]
    if dedup:
        pb["possible_duplicate_of"] = dedup
    else:
        pb.pop("possible_duplicate_of", None)


def _ensure_dup_flag_best_first(pb: dict[str, Any], best_nk: str) -> None:
    cur = pb.get("possible_duplicate_of")
    tail: list[str] = []
    if isinstance(cur, list):
        tail = [str(x).strip() for x in cur if str(x).strip() and str(x).strip() != best_nk]
    out = [best_nk] + tail[:31]
    seen: set[str] = set()
    deduped: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
        if len(deduped) >= 32:
            break
    pb["possible_duplicate_of"] = deduped


def _fully_clean_display_for_open_channel_match(display: str) -> str:
    """Collapse dash-separated segments with the same cleaning used for segment merge anchors."""
    raw = _norm_hyphens((display or "").strip())
    if not raw:
        return ""
    parts: list[str] = []
    for seg in raw.split("-"):
        c = _clean_segment(seg)
        if c:
            parts.append(c)
    return " ".join(parts).lower().strip()


def _open_channel_consolidation_hit(
    display: str,
    *,
    distributor_suggested_names: frozenset[str],
) -> bool:
    d0 = (display or "").strip()
    if not d0:
        return False
    if "open channel" in d0.lower():
        return True
    fc = _fully_clean_display_for_open_channel_match(d0)
    if fc == "channel":
        return True
    dist_clean = frozenset(
        _fully_clean_display_for_open_channel_match(x)
        for x in distributor_suggested_names
        if isinstance(x, str) and x.strip()
    )
    if fc and fc in dist_clean:
        return True
    return False


def _merge_source_bucket_into_target(
    pending: dict[str, dict[str, Any]], *, target_nk: str, src_pb: dict[str, Any]
) -> None:
    tgt = pending[target_nk]
    tgt.setdefault("line_ids", []).extend(list(src_pb.get("line_ids", [])))
    tgt["source_tokens"] = sorted(set(tgt.get("source_tokens", [])) | set(src_pb.get("source_tokens", [])))
    tq, sq = tgt.get("qty"), src_pb.get("qty")
    tgt["qty"] = (tq or Decimal(0)) + (sq or Decimal(0))
    ta, sa = tgt.get("amt"), src_pb.get("amt")
    tgt["amt"] = (ta or Decimal(0)) + (sa or Decimal(0))
    tgt["needs_name_review"] = bool(tgt.get("needs_name_review") or src_pb.get("needs_name_review"))
    samples = tgt.setdefault("samples", [])
    for s in src_pb.get("samples", []):
        if len(samples) < 5 and s not in samples:
            samples.append(s)
    dup_s = src_pb.get("possible_duplicate_of")
    if isinstance(dup_s, list) and dup_s:
        tgt.setdefault("possible_duplicate_of", []).extend(str(x) for x in dup_s if str(x).strip())
    _dedupe_dup_list(tgt)


def _rewrite_duplicate_refs(pending: dict[str, dict[str, Any]], old_nk: str, new_nk: str) -> None:
    if old_nk == new_nk:
        return
    for pb in pending.values():
        raw = pb.get("possible_duplicate_of")
        if not isinstance(raw, list) or not raw:
            continue
        repl = [new_nk if str(x).strip() == old_nk else str(x).strip() for x in raw if str(x).strip()]
        if repl:
            pb["possible_duplicate_of"] = sorted(set(repl))[:32]
        else:
            pb.pop("possible_duplicate_of", None)


def _source_should_merge_into_target(disp_s: str, disp_t: str) -> bool:
    """Prefer merging a noisier/longer dashed label into a cleaner canonical row."""
    a, b = _norm_hyphens(disp_s).strip(), _norm_hyphens(disp_t).strip()
    ca, cb = a.count("-"), b.count("-")
    if ca > cb:
        return True
    if cb > ca:
        return False
    return len(a) > len(b)


def _evaluate_segment_pass_for_source(
    nk_s: str,
    pb_s: dict[str, Any],
    pending: dict[str, dict[str, Any]],
) -> tuple[str, str | None]:
    """Returns (action, target_nk) where action in ('noop', 'merge', 'dup')."""
    if pb_s.get("special_category") in ("noise_only", "internal_note"):
        return "noop", None
    disp_s = (pb_s.get("display_suggested_name") or "").strip()
    if not disp_s:
        return "noop", None

    targets = _build_targets(pending, exclude_nk=nk_s)
    if not targets:
        return "noop", None

    segs = _usable_cleaned_segments(disp_s)
    if not segs:
        return "noop", None

    at88 = _targets_at_or_above(segs, targets, floor=_RATIO_MERGE)
    if len(at88) >= 2:
        # Ambiguous: best ratio among those ≥0.88
        best_nk = max(at88, key=lambda k: (-at88[k], k))
        _ensure_dup_flag_best_first(pb_s, best_nk)
        return "dup", None
    if len(at88) == 1:
        only = next(iter(at88))
        if only not in pending:
            return "noop", None
        disp_t = (pending[only].get("display_suggested_name") or "").strip()
        if not _source_should_merge_into_target(disp_s, disp_t):
            return "noop", None
        return "merge", only

    # No ≥0.88 hit: best across all segments × targets
    best_pair_r = 0.0
    best_nk_hint: str | None = None
    for seg in segs:
        for nk, disp, _pb in targets:
            r = _ratio(seg, disp)
            if r > best_pair_r or (r == best_pair_r and (best_nk_hint is None or nk < best_nk_hint)):
                best_pair_r = r
                best_nk_hint = nk
    if _RATIO_HINT_LO < best_pair_r < _RATIO_MERGE and best_nk_hint:
        _ensure_dup_flag_best_first(pb_s, best_nk_hint)
        return "dup", None

    return "noop", None


def _apply_segment_merge_pass(pending: dict[str, dict[str, Any]]) -> None:
    changed = True
    while changed:
        changed = False
        for nk_s in sorted(pending.keys()):
            if nk_s not in pending:
                continue
            pb_s = pending[nk_s]
            action, target_nk = _evaluate_segment_pass_for_source(nk_s, pb_s, pending)
            if action == "merge" and target_nk and target_nk in pending and target_nk != nk_s:
                _merge_source_bucket_into_target(pending, target_nk=target_nk, src_pb=pb_s)
                del pending[nk_s]
                _rewrite_duplicate_refs(pending, nk_s, target_nk)
                changed = True
                break


def _apply_open_channel_consolidation_pass(
    pending: dict[str, dict[str, Any]],
    *,
    distributor_suggested_names: frozenset[str],
) -> None:
    """Merge Open Channel–related rows (including prior ``noise_only``) into one standard customer row."""
    ocs: list[tuple[str, dict[str, Any]]] = []
    for nk, pb in pending.items():
        disp = (pb.get("display_suggested_name") or "").strip()
        if not disp:
            continue
        if _open_channel_consolidation_hit(disp, distributor_suggested_names=distributor_suggested_names):
            ocs.append((nk, pb))

    if not ocs:
        return

    merged: dict[str, Any] = {
        "line_ids": [],
        "samples": [],
        "source_tokens": [],
        "qty": Decimal(0),
        "amt": Decimal(0),
        "needs_name_review": False,
        "display_suggested_name": "Open Channel",
        "special_category": None,
    }
    all_tokens: set[str] = set()
    dup_acc: list[str] = []
    typo_acc: list[str] = []

    for nk, pb in ocs:
        merged["line_ids"].extend(list(pb.get("line_ids", [])))
        merged["qty"] += pb.get("qty") or Decimal(0)
        merged["amt"] += pb.get("amt") or Decimal(0)
        merged["needs_name_review"] = bool(merged["needs_name_review"] or pb.get("needs_name_review"))
        for t in pb.get("source_tokens", []):
            if isinstance(t, str) and t.strip():
                all_tokens.add(t.strip()[:512])
        for s in pb.get("samples", []):
            if len(merged["samples"]) < 5 and s not in merged["samples"]:
                merged["samples"].append(s)
        d = pb.get("possible_duplicate_of")
        if isinstance(d, list) and d:
            dup_acc.extend(str(x) for x in d if str(x).strip())
        ty = pb.get("typo_suspected_of")
        if isinstance(ty, list) and ty:
            typo_acc.extend(str(x) for x in ty if str(x).strip())

    merged["source_tokens"] = sorted(all_tokens)
    if dup_acc:
        merged["possible_duplicate_of"] = sorted(set(dup_acc))[:32]
    if typo_acc:
        merged["typo_suspected_of"] = sorted(set(typo_acc))[:32]

    for nk, _pb in ocs:
        del pending[nk]

    src_sorted = merged["source_tokens"]
    new_nk = grouped_candidate_normalized_key(
        suggested_name="Open Channel",
        source_tokens=src_sorted,
        special_category=None,
    )[:512]

    if new_nk in pending:
        existing = pending[new_nk]
        existing.setdefault("line_ids", []).extend(merged["line_ids"])
        existing["source_tokens"] = sorted(set(existing.get("source_tokens", [])) | set(src_sorted))
        existing["qty"] = (existing.get("qty") or Decimal(0)) + (merged["qty"] or Decimal(0))
        existing["amt"] = (existing.get("amt") or Decimal(0)) + (merged["amt"] or Decimal(0))
        existing["needs_name_review"] = bool(existing.get("needs_name_review") or merged["needs_name_review"])
        for s in merged.get("samples", []):
            ss = existing.setdefault("samples", [])
            if len(ss) < 5 and s not in ss:
                ss.append(s)
        if merged.get("possible_duplicate_of"):
            existing.setdefault("possible_duplicate_of", []).extend(merged["possible_duplicate_of"])
            _dedupe_dup_list(existing)
        if merged.get("typo_suspected_of"):
            existing.setdefault("typo_suspected_of", []).extend(merged["typo_suspected_of"])
            raw_t = existing.get("typo_suspected_of")
            if isinstance(raw_t, list) and raw_t:
                existing["typo_suspected_of"] = sorted({str(x) for x in raw_t if str(x).strip()})[:32]
            else:
                existing.pop("typo_suspected_of", None)
        if (existing.get("display_suggested_name") or "").strip().lower() != "open channel":
            existing["display_suggested_name"] = "Open Channel"
        existing.pop("special_category", None)
    else:
        pending[new_nk] = merged


def apply_intra_job_remainder_merge_pass(
    pending: dict[str, dict[str, Any]],
    *,
    distributor_suggested_names: frozenset[str] | set[str] | None = None,
) -> None:
    """Run segment-based merge, then Open Channel consolidation, mutating ``pending`` in place."""
    dn = frozenset(str(x).strip()[:256] for x in (distributor_suggested_names or ()) if str(x).strip())
    _apply_segment_merge_pass(pending)
    _apply_open_channel_consolidation_pass(pending, distributor_suggested_names=dn)

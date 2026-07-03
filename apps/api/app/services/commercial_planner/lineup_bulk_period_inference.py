"""Layered period inference for bulk historical lineup backfill (Spec C §3.2).

Priority: folder path → title band (F1) → filename → manual steward entry.
``1H`` always expands to Q1 + Q2. Conflicting quarter/year signals across tiers
surface ``period_signal_conflict`` — never silently auto-picked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.commercial_planner.lineup_half_year_quantity import PERIOD_SCOPE_1H_SPLIT_FLAG
from app.services.commercial_planner.lineup_period_inference import _parse_label, _quarter_start_month

_TITLE_BAND_RE = re.compile(
    r"(?:20\d{2}|\b\d{2}\b)\s*(?:1\s*h|1h|h\s*1)\b|"
    r"(?:20\d{2}|\b\d{2}\b)\s*q\s*([1-4])\b|"
    r"q\s*([1-4])\s*(?:20\d{2}|\b\d{2}\b)",
    re.IGNORECASE,
)
_FOLDER_YEAR_RE = re.compile(r"(20\d{2})")
_FOLDER_QUARTER_RE = re.compile(r"\bQ\s*([1-4])\b", re.IGNORECASE)
_FOLDER_HALF_RE = re.compile(r"\b1\s*H\b|\bH\s*1\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PeriodSignal:
    tier: str  # folder | title_band | filename | manual
    label: str | None
    year: int | None
    quarter: int | None
    is_half: bool = False


@dataclass
class LayeredPeriodAssignment:
    period_label: str | None
    period_start: date | None
    source_tier: str | None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_label": self.period_label,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "source_tier": self.source_tier,
            "flags": list(self.flags),
        }


def _two_digit_year(y: int) -> int:
    return y if y >= 100 else 2000 + y


def _signal_from_label(text: str | None, tier: str) -> PeriodSignal | None:
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    if _FOLDER_HALF_RE.search(s):
        year, _, _ = _parse_label(s)
        if year is None:
            m = _FOLDER_YEAR_RE.search(s)
            year = int(m.group(1)) if m else None
        return PeriodSignal(tier=tier, label=s[:64], year=year, quarter=None, is_half=True)
    year, quarter, _month = _parse_label(s)
    if year is None and quarter is None:
        m = _TITLE_BAND_RE.search(s)
        if not m:
            return None
        if m.group(0).lower().replace(" ", "").find("1h") >= 0 or "h1" in m.group(0).lower().replace(" ", ""):
            ym = _FOLDER_YEAR_RE.search(s)
            year = int(ym.group(1)) if ym else None
            return PeriodSignal(tier=tier, label=s[:64], year=year, quarter=None, is_half=True)
        q = m.group(1) or m.group(2)
        quarter = int(q) if q else None
        ym = _FOLDER_YEAR_RE.search(s)
        year = year or (int(ym.group(1)) if ym else None)
    return PeriodSignal(tier=tier, label=s[:64], year=year, quarter=quarter, is_half=False)


def infer_period_from_folder_path(folder_path: str | None) -> PeriodSignal | None:
    if not folder_path:
        return None
    path = str(folder_path).replace("/", "\\")
    return _signal_from_label(path, "folder")


def infer_period_from_title_band(title_band: str | None) -> PeriodSignal | None:
    return _signal_from_label(title_band, "title_band")


def infer_period_from_filename(filename: str | None) -> PeriodSignal | None:
    if not filename:
        return None
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return _signal_from_label(stem, "filename")


def scan_title_band_from_workbook_rows(rows: list[list[Any]], *, max_rows: int = 6) -> str | None:
    """Scan the first rows (F1-style band) for a YYYY 1H / Qn NEW PLAN style title."""
    for row in rows[:max_rows]:
        for cell in row:
            if cell is None:
                continue
            text = str(cell).strip()
            if not text:
                continue
            if _TITLE_BAND_RE.search(text) or _FOLDER_HALF_RE.search(text):
                return text[:256]
            if _FOLDER_YEAR_RE.search(text) and re.search(r"q\s*[1-4]|1\s*h", text, re.I):
                return text[:256]
    return None


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year} Q{quarter}"


def _assignments_from_signal(signal: PeriodSignal, flags: list[str]) -> list[LayeredPeriodAssignment]:
    if signal.is_half:
        if signal.year is None:
            return [
                LayeredPeriodAssignment(
                    period_label=signal.label,
                    period_start=None,
                    source_tier=signal.tier,
                    flags=flags + ["period_year_unknown"],
                )
            ]
        y = _two_digit_year(int(signal.year))
        return [
            LayeredPeriodAssignment(
                period_label=_quarter_label(y, 1),
                period_start=date(y, 1, 1),
                source_tier=signal.tier,
                flags=list(flags) + ["period_half_split_q1"],
            ),
            LayeredPeriodAssignment(
                period_label=_quarter_label(y, 2),
                period_start=date(y, 4, 1),
                source_tier=signal.tier,
                flags=list(flags) + ["period_half_split_q2"],
            ),
        ]
    if signal.year is None:
        return [
            LayeredPeriodAssignment(
                period_label=signal.label,
                period_start=None,
                source_tier=signal.tier,
                flags=flags + ["period_year_unknown"],
            )
        ]
    y = _two_digit_year(int(signal.year))
    if signal.quarter is None:
        return [
            LayeredPeriodAssignment(
                period_label=str(signal.label or y),
                period_start=date(y, 1, 1),
                source_tier=signal.tier,
                flags=flags + ["period_quarter_unknown"],
            )
        ]
    q = int(signal.quarter)
    return [
        LayeredPeriodAssignment(
            period_label=_quarter_label(y, q),
            period_start=date(y, _quarter_start_month(q), 1),
            source_tier=signal.tier,
            flags=list(flags),
        )
    ]


def _quarters_conflict(a: PeriodSignal, b: PeriodSignal) -> bool:
    if a.is_half or b.is_half:
        return False
    if a.year is not None and b.year is not None and _two_digit_year(a.year) != _two_digit_year(b.year):
        return True
    if a.quarter is not None and b.quarter is not None and a.quarter != b.quarter:
        return True
    return False


def resolve_layered_period(
    *,
    folder_path: str | None = None,
    filename: str | None = None,
    title_band: str | None = None,
    manual_period_label: str | None = None,
) -> tuple[list[LayeredPeriodAssignment], dict[str, Any]]:
    """Return one or two period assignments (1H split) plus diagnostic report."""
    signals: list[PeriodSignal] = []
    if manual_period_label and str(manual_period_label).strip():
        sig = _signal_from_label(manual_period_label, "manual")
        if sig:
            signals = [sig]
    else:
        for fn, tier in (
            (infer_period_from_folder_path(folder_path), "folder"),
            (infer_period_from_title_band(title_band), "title_band"),
            (infer_period_from_filename(filename), "filename"),
        ):
            if fn is not None:
                signals.append(fn)

    report: dict[str, Any] = {
        "signals": [
            {
                "tier": s.tier,
                "label": s.label,
                "year": s.year,
                "quarter": s.quarter,
                "is_half": s.is_half,
            }
            for s in signals
        ]
    }

    if not signals:
        return (
            [
                LayeredPeriodAssignment(
                    period_label=None,
                    period_start=None,
                    source_tier=None,
                    flags=["period_unknown"],
                )
            ],
            report,
        )

    anchor = signals[0]
    half_sig = next((s for s in signals if s.is_half), None)

    # 1H from ANY tier triggers Q1+Q2 split; folder anchors year (and quarter when present).
    if half_sig is not None:
        year: int | None = None
        for s in signals:
            if s.year is not None:
                year = _two_digit_year(int(s.year))
                break
        if year is None:
            return (
                [
                    LayeredPeriodAssignment(
                        period_label=half_sig.label,
                        period_start=None,
                        source_tier=anchor.tier,
                        flags=[PERIOD_SCOPE_1H_SPLIT_FLAG, "period_year_unknown"],
                    )
                ],
                report,
            )

        split_flags = [PERIOD_SCOPE_1H_SPLIT_FLAG]
        if half_sig.tier != anchor.tier:
            report["half_trigger_tier"] = half_sig.tier

        assignments = [
            LayeredPeriodAssignment(
                period_label=_quarter_label(year, 1),
                period_start=date(year, 1, 1),
                source_tier=anchor.tier,
                flags=split_flags + ["period_half_split_q1"],
            ),
            LayeredPeriodAssignment(
                period_label=_quarter_label(year, 2),
                period_start=date(year, 4, 1),
                source_tier=anchor.tier,
                flags=split_flags + ["period_half_split_q2"],
            ),
        ]
        report["winning_tier"] = anchor.tier
        report["half_split"] = True
        return assignments, report

    flags: list[str] = []
    winner = anchor
    for other in signals[1:]:
        if _quarters_conflict(winner, other):
            flags.append("period_signal_conflict")
            report["conflict"] = {"primary": winner.tier, "other": other.tier}
            return (
                [
                    LayeredPeriodAssignment(
                        period_label=None,
                        period_start=None,
                        source_tier=None,
                        flags=flags,
                    )
                ],
                report,
            )

    assignments = _assignments_from_signal(winner, flags)
    report["winning_tier"] = winner.tier
    return assignments, report

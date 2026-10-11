"""One shipment's receipt read: identity, delivery siblings, and derived changes."""

from __future__ import annotations

from typing import Any

from app.services.imports.shipment_evidence_line_identity import stable_line_identity_key_from_mapping


def receipt_line_identity(values: dict[str, Any]) -> str:
    return stable_line_identity_key_from_mapping(values)


def receipt_group(values: dict[str, Any]) -> str:
    """How sibling lines are chosen. A delivery is the shipment; otherwise the order; otherwise this line."""
    if str(values.get("delivery_no") or "").strip():
        return "delivery"
    if str(values.get("order_no") or "").strip():
        return "order"
    return "line"


def reports_oldest_first(rows: list[tuple[int, Any, str]]) -> list[set[str]]:
    """Group observation rows into reports. A report is one import job, oldest first."""
    buckets: dict[int, list[tuple[Any, str]]] = {}
    for job_id, valid_from, key in rows:
        buckets.setdefault(int(job_id), []).append((valid_from, key))
    ordered = sorted(
        buckets.items(),
        key=lambda item: (min(valid_from for valid_from, _key in item[1]), item[0]),
    )
    return [{key for _valid_from, key in pairs} for _job_id, pairs in ordered]


def vanished_line_keys(reports: list[set[str]]) -> set[str]:
    """A line is a cancelled candidate when an earlier report of this shipment had it and the latest report does not.

    One report is not a signal: there is no next report for the line to vanish from.
    A line that is back on the latest report is not a candidate.
    """
    if len(reports) < 2:
        return set()
    earlier: set[str] = set()
    for report in reports[:-1]:
        earlier.update(report)
    return earlier - reports[-1]

"""Parse a customer campaign / pillar calendar through a mapping profile.

Reuses the payment-evidence parser's cell and date helpers so a header, a date format or an Excel
date cell is read the same way on every CPOR upload. A workbook, a CSV or an already-read grid
all end in ``parse_calendar_grid``.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.cpor.customer_calendar.profiles import (
    CALENDAR_FIELDS,
    CALENDAR_KINDS,
    REQUIRED_FIELDS,
    normalize_header,
)
from app.services.cpor.payment_evidence.parser import _as_date, _cell_str

_norm = normalize_header


def _build_index(
    headers: list[Any], column_map: dict[str, list[str]]
) -> tuple[dict[str, int], dict[str, list[str]]]:
    """(canonical field -> column index, field -> headers that tie for that match).

    The first alias (in the profile's order) that matches a header wins, headers compared with
    ``normalize_header``. When the matched header text appears in more than one column the match
    is ambiguous: the field is reported in the second dict instead of silently reading the first.
    """
    norm_headers = [normalize_header(h) for h in headers]
    out: dict[str, int] = {}
    ambiguous: dict[str, list[str]] = {}
    for field in CALENDAR_FIELDS:
        for alias in column_map.get(field) or []:
            want = normalize_header(alias)
            hits = [i for i, h in enumerate(norm_headers) if want and h == want]
            if not hits:
                continue
            if hits[0] in out.values():
                break
            out[field] = hits[0]
            if len(hits) > 1:
                ambiguous[field] = [str(headers[i]) for i in hits]
            break
    return out, ambiguous


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _map_kind(raw: str | None, kind_map: dict[str, str]) -> str:
    key = _norm(raw)
    if not key:
        return "other"
    mapped = {_norm(k): v for k, v in kind_map.items()}.get(key)
    if mapped in CALENDAR_KINDS:
        return mapped
    return key if key in CALENDAR_KINDS else "other"


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def parse_calendar_grid(grid: list[list[Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Parse rows (a list of cell lists, header at ``header_row_index``, 1-based).

    Returns ``{ok, events, row_errors, blocking_errors, headers, mapped_columns, row_count}``.
    A blocking error (no data, header row missing, a required column not found) stops the upload;
    a row error drops that row and is listed in the preview so the rest can still be applied.
    """
    column_map: dict[str, list[str]] = dict(profile.get("column_map_json") or {})
    kind_map: dict[str, str] = dict((profile.get("value_maps_json") or {}).get("kind") or {})
    header_row_index = int(profile.get("header_row_index") or 1)

    result: dict[str, Any] = {
        "ok": False,
        "events": [],
        "row_errors": [],
        "blocking_errors": [],
        "headers": [],
        "mapped_columns": {},
        "row_count": 0,
        "profile_code": profile.get("profile_code"),
    }
    if not grid or all(all(_blank(c) for c in (row or [])) for row in grid):
        result["blocking_errors"].append({"code": "empty_file", "message": "The file has no rows"})
        return result
    if header_row_index > len(grid):
        result["blocking_errors"].append(
            {
                "code": "header_row_missing",
                "message": f"The file has no row {header_row_index} to use as headers",
            }
        )
        return result

    headers = list(grid[header_row_index - 1] or [])
    result["headers"] = [str(h) if h is not None else "" for h in headers]
    index, ambiguous = _build_index(headers, column_map)
    result["mapped_columns"] = {f: result["headers"][i] for f, i in index.items()}
    for field, tied in ambiguous.items():
        result["blocking_errors"].append(
            {
                "code": f"ambiguous_{field}_column",
                "message": (
                    f"More than one column matches the {field.replace('_', ' ')} mapping "
                    f"({', '.join(repr(h) for h in tied)}); rename or remove the duplicate "
                    "column so the intended one is read"
                ),
            }
        )
    for field in REQUIRED_FIELDS:
        if field not in index:
            result["blocking_errors"].append(
                {
                    "code": f"missing_{field}_column",
                    "message": (
                        f"No column matches the {field.replace('_', ' ')} mapping "
                        f"({', '.join(column_map.get(field) or [])})"
                    ),
                }
            )
    if result["blocking_errors"]:
        return result

    def fail(row_no: int, code: str, message: str) -> None:
        result["row_errors"].append({"row": row_no, "code": code, "message": message})

    def cell(row: list[Any], field: str) -> Any:
        j = index.get(field)
        return row[j] if j is not None and j < len(row) else None

    for offset, row in enumerate(grid[header_row_index:], start=header_row_index + 1):
        row = list(row or [])
        if all(_blank(c) for c in row):
            continue

        name = _cell_str(cell(row, "name"))
        if not name:
            fail(offset, "missing_name", "No event name")
            continue
        raw_start, raw_end = cell(row, "start_date"), cell(row, "end_date")
        if _blank(raw_start):
            fail(offset, "missing_start_date", "No start date")
            continue
        start = _as_date(raw_start)
        if start is None:
            fail(offset, "bad_start_date", f"Start date {str(raw_start)!r} is not a date")
            continue
        if _blank(raw_end):
            end = start
        else:
            end = _as_date(raw_end)
            if end is None:
                fail(offset, "bad_end_date", f"End date {str(raw_end)!r} is not a date")
                continue
        if end < start:
            fail(offset, "end_before_start", "End date is before the start date")
            continue

        result["events"].append(
            {
                "row_number": offset,
                "customer_token": _cell_str(cell(row, "customer_token")),
                "name": name[:256],
                "kind": _map_kind(_cell_str(cell(row, "kind")), kind_map),
                "start_date": start,
                "end_date": end,
                "raw_row": {
                    str(headers[j]): _json_safe(row[j])
                    for j in range(min(len(headers), len(row)))
                    if not _blank(headers[j])
                },
            }
        )

    result["row_count"] = len(result["events"])
    result["ok"] = True
    return result


def parse_calendar_csv(data: bytes, profile: dict[str, Any]) -> dict[str, Any]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    grid = [list(r) for r in csv.reader(io.StringIO(text), dialect)]
    return parse_calendar_grid(grid, profile)


def parse_calendar_workbook(data: bytes, profile: dict[str, Any]) -> dict[str, Any]:
    from openpyxl import load_workbook

    # Keep styles: openpyxl uses the number format to convert Excel serial dates.
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        wanted = (profile.get("sheet_name") or "").strip()
        if wanted and wanted not in wb.sheetnames:
            return {
                "ok": False,
                "events": [],
                "row_errors": [],
                "blocking_errors": [
                    {"code": "sheet_missing", "message": f"Sheet {wanted!r} is not in the workbook"}
                ],
                "headers": [],
                "mapped_columns": {},
                "row_count": 0,
                "profile_code": profile.get("profile_code"),
            }
        ws = wb[wanted] if wanted else wb[wb.sheetnames[0]]
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return parse_calendar_grid(grid, profile)


def parse_calendar_file(filename: str, data: bytes, profile: dict[str, Any]) -> dict[str, Any]:
    """Dispatch on the file extension: .csv/.txt as text, anything else as a workbook."""
    name = (filename or "").lower()
    if name.endswith((".csv", ".txt")):
        return parse_calendar_csv(data, profile)
    try:
        return parse_calendar_workbook(data, profile)
    except Exception as exc:  # noqa: BLE001 - an unreadable workbook is a blocking error, not a 500
        return {
            "ok": False,
            "events": [],
            "row_errors": [],
            "blocking_errors": [
                {
                    "code": "unreadable_file",
                    "message": f"Could not read the file: {type(exc).__name__}",
                }
            ],
            "headers": [],
            "mapped_columns": {},
            "row_count": 0,
            "profile_code": profile.get("profile_code"),
        }

"""HTML + text/plain renderer for the shipping digest. No placeholder copy."""

from __future__ import annotations

import html
from typing import Any

from app.services.shipping_digest.build import rows_by_distributor, section_dims

_DETAIL_COLUMNS = ("customer", "date", "sales_model", "qty")
_LABELS = {
    "distributor": "Distributor",
    "customer": "Customer",
    "date": "Date",
    "sales_model": "Sales model",
    "qty": "Qty",
}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _dims_for_section(section: dict[str, Any], vintage: dict[str, Any]) -> dict[str, Any]:
    sid = str(section.get("id") or "")
    raw = (vintage.get("section_dims") or {}).get(sid) if isinstance(vintage.get("section_dims"), dict) else None
    if isinstance(raw, dict) and "rows" in raw:
        return raw
    return section_dims(list(section.get("rows") or []))


def render_html(digest: dict[str, Any]) -> str:
    vintage = digest.get("data_vintage") or {}
    recipients = digest.get("intended_recipients") or []
    sections = list(digest.get("sections") or [])
    summary_rows = "".join(
        (
            "<tr>"
            f"<td>{_cell(s.get('title'))}</td>"
            f"<td style='text-align:right'>{_cell(d.get('rows'))}</td>"
            f"<td style='text-align:right'>{_cell(d.get('distis'))}</td>"
            f"<td style='text-align:right'>{_cell(d.get('customers'))}</td>"
            f"<td style='text-align:right'>{_cell(d.get('models'))}</td>"
            f"<td style='text-align:right'>{_cell(d.get('qty'))}</td>"
            "</tr>"
        )
        for s in sections
        for d in [_dims_for_section(s, vintage)]
    )
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:Segoe UI,Arial,sans-serif;font-size:13px;color:#1a1a1a;margin:24px;}",
        "h1{font-size:20px;margin:0 0 8px;}",
        "h2{font-size:15px;margin:24px 0 8px;}",
        "h3{font-size:13px;margin:16px 0 0;padding:8px 10px;background:#1f4e79;color:#fff;}",
        ".meta{color:#555;margin:0 0 16px;}",
        "table{border-collapse:collapse;width:100%;margin:0 0 16px;}",
        "th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top;}",
        "th{background:#f3f3f3;}",
        ".summary td{border:1px solid #ddd;}",
        "</style></head><body>",
        f"<h1>{_cell(digest.get('title') or 'Shipping digest')}</h1>",
        "<p class='meta'>As of {as_of} · source job {job} · this week {this_w} · next week {next_w}</p>".format(
            as_of=_cell(vintage.get("as_of_utc")),
            job=_cell(vintage.get("source_job_id")),
            this_w=_cell(vintage.get("this_week")),
            next_w=_cell(vintage.get("next_week")),
        ),
        "<p class='meta'>Would send To: {to}</p>".format(to=_cell(", ".join(str(x) for x in recipients))),
        "<p class='meta'>Within each section, lines are grouped by distributor, then sorted by customer "
        "(qty summed at distributor × customer × date × sales model). "
        "ETA changes skip unusable snapshots (jobs with no POD and no Est POD)"
        "{skip}.</p>".format(
            skip=(
                f"; skipped job ids {vintage.get('skipped_unusable_job_ids')}"
                if vintage.get("skipped_unusable_job_ids")
                else ""
            )
        ),
        "<h2>Summary</h2>",
        "<table class='summary'><thead><tr>"
        "<th>Section</th><th>Rows</th><th>Distis</th><th>Customers</th><th>Models</th><th>Qty</th>"
        "</tr></thead><tbody>",
        summary_rows,
        "</tbody></table>",
    ]
    for section in sections:
        rows = section.get("rows") or []
        parts.append(f"<h2>{_cell(section.get('title'))} ({len(rows)})</h2>")
        if not rows:
            parts.append("<p class='meta'>None.</p>")
            continue
        for dist_name, dist_rows in rows_by_distributor(list(rows)):
            dims = section_dims(dist_rows)
            parts.append(
                f"<h3>{_cell(dist_name)} · {dims['rows']} lines · {dims['customers']} customers · qty {dims['qty']}</h3>"
            )
            parts.append("<table><thead><tr>")
            for col in _DETAIL_COLUMNS:
                parts.append(f"<th>{_LABELS[col]}</th>")
            parts.append("</tr></thead><tbody>")
            for row in dist_rows:
                parts.append("<tr>")
                for col in _DETAIL_COLUMNS:
                    parts.append(f"<td>{_cell(row.get(col))}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "".join(parts)


def render_text(digest: dict[str, Any]) -> str:
    vintage = digest.get("data_vintage") or {}
    recipients = digest.get("intended_recipients") or []
    lines = [
        str(digest.get("title") or "Shipping digest"),
        f"As of {vintage.get('as_of_utc')} · source job {vintage.get('source_job_id')}",
        f"This week {vintage.get('this_week')} · next week {vintage.get('next_week')}",
        "Would send To: " + ", ".join(str(x) for x in recipients),
        "Grouped by distributor, then sorted by customer (qty summed).",
        "",
        "Summary (rows = disti × customer × date × model, qty summed)",
    ]
    for section in digest.get("sections") or []:
        d = _dims_for_section(section, vintage)
        lines.append(
            f"  {section.get('title')}: {d.get('rows')} rows · "
            f"{d.get('distis')} distis · {d.get('customers')} customers · "
            f"{d.get('models')} models · qty {d.get('qty')}"
        )
    lines.append("")
    for section in digest.get("sections") or []:
        rows = section.get("rows") or []
        lines.append(f"{section.get('title')} ({len(rows)})")
        if not rows:
            lines.append("None.")
            lines.append("")
            continue
        for dist_name, dist_rows in rows_by_distributor(list(rows)):
            dims = section_dims(dist_rows)
            lines.append(f"  {dist_name} · {dims['rows']} lines · {dims['customers']} customers · qty {dims['qty']}")
            lines.append("\t" + "\t".join(_LABELS[c] for c in _DETAIL_COLUMNS))
            for row in dist_rows:
                lines.append(
                    "\t"
                    + "\t".join("" if row.get(c) is None else str(row.get(c)) for c in _DETAIL_COLUMNS)
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

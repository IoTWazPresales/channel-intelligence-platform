"""Shipping digest preview (BACKLOG-132 Unit B) — no SMTP."""

from __future__ import annotations

from pathlib import Path

from app.services.shipping_digest.build import group_line_rows, section_dims
from app.services.shipping_digest.recipients import (
    DEFAULT_SHIPPING_MAILER_RECIPIENTS,
    intended_mailer_recipients,
)
from app.services.shipping_digest.render import render_html, render_text

_COLS = ("distributor", "customer", "date", "sales_model", "qty")


def _digest() -> dict:
    return {
        "title": "Shipping digest",
        "data_vintage": {
            "as_of_utc": "2026-08-18T10:00:00+00:00",
            "source_job_id": 1159,
            "reference_date": "2026-08-18",
            "this_week": "2026-08-17…2026-08-23",
            "next_week": "2026-08-24…2026-08-30",
            "section_counts": {
                "arriving_week": 1,
                "arriving_next_week": 1,
                "newly_landed": 1,
                "eta_changes": 1,
            },
        },
        "intended_recipients": list(DEFAULT_SHIPPING_MAILER_RECIPIENTS),
        "sections": [
            {
                "id": "arriving_week",
                "title": "Stock with ETA this week (not yet POD'd)",
                "rows": [
                    {
                        "distributor": "Mustek",
                        "customer": "Game",
                        "date": "2026-08-19",
                        "sales_model": "UX3402VA",
                        "qty": 2,
                    }
                ],
            },
            {
                "id": "arriving_next_week",
                "title": "Stock with ETA next week (not yet POD'd)",
                "rows": [
                    {
                        "distributor": "Pinnacle",
                        "customer": "Amazon",
                        "date": "2026-08-26",
                        "sales_model": "FX608JHI",
                        "qty": 24,
                    }
                ],
            },
            {
                "id": "newly_landed",
                "title": "Stock POD'd that was not POD'd on the last report",
                "rows": [
                    {
                        "distributor": "ACZA",
                        "customer": "Incredible",
                        "date": "2026-08-17",
                        "sales_model": "Vivobook",
                        "qty": 1,
                    }
                ],
            },
            {
                "id": "eta_changes",
                "title": "ETA changes vs last usable report (still open)",
                "rows": [
                    {
                        "distributor": "Rectron",
                        "customer": "Takealot",
                        "date": "2026-08-10 → 2026-09-25",
                        "sales_model": "Zenscreen",
                        "qty": 4,
                    }
                ],
            },
        ],
    }


def test_intended_recipients_are_the_five() -> None:
    rec = intended_mailer_recipients()
    assert "Warren_Eliason@asus.com" in rec
    assert "Leigh_Sharpe@asus.com" in rec
    assert len(rec) >= 5


def test_renderer_three_sections_no_placeholder() -> None:
    digest = _digest()
    html = render_html(digest)
    text = render_text(digest)
    assert "Stock with ETA this week" in html and "Stock with ETA this week" in text
    assert "Stock with ETA next week" in html and "Stock with ETA next week" in text
    assert "POD" in html and "POD" in text
    assert "ETA changes vs last usable report" in html
    assert "Summary" in html and "Summary" in text
    assert "Distis" in html and "Customers" in html and "Models" in html
    assert "1 distis · 1 customers · 1 models" in text
    assert "UX3402VA" in html
    assert "<h3>Mustek" in html
    assert "<h3>Pinnacle" in html
    assert "<h3>ACZA" in html
    assert "Would send To:" in text
    assert "Leigh_Sharpe@asus.com" in text
    for tok in ("lorem", "placeholder", "pending owner"):
        assert tok not in html.lower()
        assert tok not in text.lower()
    for col in ("Customer", "Date", "Sales model", "Qty"):
        assert col in html
        assert col in text
    for row in digest["sections"]:
        for line in row["rows"]:
            for k in _COLS:
                assert k in line


def test_dsi_apply_does_not_import_digest() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "imports"
        / "dsi_apply_completion.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "shipping_digest" not in text
    assert "dispatch_shipping_digest" not in text


def test_shipment_apply_wires_preview_dispatch() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "imports"
        / "shipment_apply_sync.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "dispatch_shipping_digest" in text
    assert "dsi_apply_completion" not in text


def test_digest_eta_is_job_scoped_not_lifetime_facts() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "shipping_digest"
        / "build.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "identity_scope_for_job" in text
    assert "import_jobs_unusable_date_snapshots" in text
    assert "open_only=True" in text
    assert "fact_evidence_scope_stmt" not in text
    assert "predicate_arriving_week" not in text


def test_group_line_rows_sums_qty_at_digest_grain() -> None:
    rows = [
        {
            "distributor": "ACZA",
            "customer": "Game",
            "date": "2026-08-17",
            "sales_model": "UX3402VA",
            "qty": 2,
        },
        {
            "distributor": "ACZA",
            "customer": "Game",
            "date": "2026-08-17",
            "sales_model": "UX3402VA",
            "qty": 3,
        },
        {
            "distributor": "Mustek",
            "customer": "Game",
            "date": "2026-08-17",
            "sales_model": "UX3402VA",
            "qty": 1,
        },
    ]
    grouped = group_line_rows(rows)
    assert len(grouped) == 2
    assert [r["distributor"] for r in grouped] == ["ACZA", "Mustek"]
    by_dist = {r["distributor"]: r["qty"] for r in grouped}
    assert by_dist["ACZA"] == 5.0
    assert by_dist["Mustek"] == 1.0
    dims = section_dims(grouped)
    assert dims["rows"] == 2
    assert dims["distis"] == 2
    assert dims["customers"] == 1
    assert dims["models"] == 1
    assert dims["qty"] == 6.0


def test_group_line_rows_sorts_disti_then_customer() -> None:
    rows = [
        {
            "distributor": "Mustek",
            "customer": "Zebra",
            "date": "2026-08-20",
            "sales_model": "B",
            "qty": 1,
        },
        {
            "distributor": "ACZA",
            "customer": "Game",
            "date": "2026-08-19",
            "sales_model": "A",
            "qty": 2,
        },
        {
            "distributor": "Mustek",
            "customer": "Amazon",
            "date": "2026-08-21",
            "sales_model": "C",
            "qty": 3,
        },
    ]
    grouped = group_line_rows(rows)
    assert [(r["distributor"], r["customer"]) for r in grouped] == [
        ("ACZA", "Game"),
        ("Mustek", "Amazon"),
        ("Mustek", "Zebra"),
    ]
    from app.services.shipping_digest.build import rows_by_distributor

    blocks = rows_by_distributor(grouped)
    assert [name for name, _ in blocks] == ["ACZA", "Mustek"]
    assert [r["customer"] for r in blocks[1][1]] == ["Amazon", "Zebra"]

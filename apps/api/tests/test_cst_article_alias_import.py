"""Unit tests for SCM article-alias workbook parse + import grouping (no cip)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

from openpyxl import Workbook

from app.services.imports.cst_article_alias_import import (
    CUSTOMER_NAME_CANON,
    import_article_alias_rows,
    parse_article_alias_workbook,
)


def _xlsx_bytes(rows: list[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_article_alias_workbook_canonical_headers():
    raw = _xlsx_bytes(
        [
            ("Customer", "Article code", "Sales Model name"),
            ("Game", "850039776", "E1504FA-382B1W"),
            ("Game Online", "850038868", "X1504VA-NJ58256W"),
        ]
    )
    rows = parse_article_alias_workbook(raw)
    assert len(rows) == 2
    assert rows[0]["customer"] == "Game"
    assert rows[0]["article"] == "850039776"
    assert rows[1]["customer"] == "Game Online"


def test_game_online_canon_maps_to_game():
    assert CUSTOMER_NAME_CANON["game online"] == "Game"


def test_import_skips_collision_same_article_two_models():
    session = MagicMock()
    # customer resolve → 57
    cust = MagicMock()
    cust.id = 57
    session.scalar.side_effect = [cust, None]  # customer then existing alias miss — but we collide first

    rows = [
        {"customer": "Game", "article": "850038868", "sales_model": "MODEL-A"},
        {"customer": "Game", "article": "850038868", "sales_model": "MODEL-B"},
    ]

    with patch(
        "app.services.imports.cst_article_alias_import._load_product_resolution_index",
        return_value=MagicMock(),
    ), patch(
        "app.services.imports.cst_article_alias_import._resolve_customer_id",
        return_value=57,
    ), patch(
        "app.services.imports.cst_article_alias_import.resolve_product_id_single_match",
        return_value=1,
    ):
        summary = import_article_alias_rows(session, rows, source="scm_upload")

    assert summary.collisions == 1
    assert summary.proposed == 0
    session.add.assert_not_called()

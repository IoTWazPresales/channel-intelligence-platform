"""GOV-008 independent probe (2026-11-02), E2 XLSX literal safety.

Builds workbooks through the real exporters (pure function and the four HTTP paths) and
inspects openpyxl data_type plus raw sheet XML. Fictional rows only, cip_test outer rollback.
Run from apps/api with -p tests.conftest (see gov008_commands.txt).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401

OUT = []

LABELS = [
    "=1+1", "+cmd|' /C calc'!A0", "-2+3", "@SUM(A1)", "\t=1+1", "\r=1+1",
    '=HYPERLINK("https://example.invalid/","fictional")', "#N/A", "#DIV/0!", " =1+1", "=1+1\n",
]


def _xml_has_formula(content: bytes) -> bool:
    with ZipFile(BytesIO(content)) as z:
        return any(b"<f>" in z.read(n) or b"<f " in z.read(n) for n in z.namelist() if n.startswith("xl/worksheets/"))


def test_pure_builder_label_and_number_types():
    from app.services.report_export import build_xlsx_bytes
    results = []
    for label in LABELS:
        rows = [{label: label, "int": 17, "neg": -12.5, "dec": Decimal("123.45"), "flag": True,
                 "none": None, "day": date(2026, 1, 5), "ts": datetime(2026, 1, 5, 7, 0)}]
        content = build_xlsx_bytes(title=label, metric_key=label, grains=[label], value=label,
                                   rows=rows, data_vintage={"note": label})
        wb = load_workbook(BytesIO(content))
        data = wb["Data"]
        keys = list(rows[0].keys())  # written in this order; read back by position
        row = {k: data.cell(2, i + 1) for i, k in enumerate(keys)}
        cover_a1 = wb["Cover"]["A1"]
        results.append({
            "label": label,
            "cover_A1": [cover_a1.value == label, cover_a1.data_type, repr(cover_a1.value)],
            "header_type": [data.cell(1, 1).data_type, repr(data.cell(1, 1).value)],
            "label_cell": [row[label].value == label, row[label].data_type, repr(row[label].value)],
            "xml_formula": _xml_has_formula(content),
            "any_f": any(c.data_type == "f" for s in wb for r in s for c in r),
            "numbers": {k: [repr(row[k].value), row[k].data_type] for k in ("int", "neg", "dec", "flag", "none", "day", "ts")},
        })
    OUT.append({"pure": results})
    assert all(r["cover_A1"][1] == "s" and r["label_cell"][1] == "s" and not r["xml_formula"] and not r["any_f"] for r in results)


@pytest.mark.anyio
async def test_http_paths_keep_formula_text_literal(signed_in):
    from sqlalchemy import select
    from app.api.deps import get_db
    from app.main import app
    from app.models.dimensions import DimCustomer
    from app.query.cache import clear_query_cache

    s = signed_in
    headers = s.headers["admin"]
    report = []
    for label in ["=1+1", "-2+3", "@SUM(A1)", "\t=1+1", '=HYPERLINK("https://example.invalid/","x")', "+cmd"]:
        async for db in app.dependency_overrides[get_db]():
            customer = (await db.scalars(select(DimCustomer).where(DimCustomer.tenant_id == s.products[0].tenant_id))).first()
            customer.name = label
            await db.commit()
        clear_query_cache()
        q = {"metric": "sellout_units", "grains": ["customer"], "filters": {}}
        paths = {}
        r = await s.client.post("/api/v1/reports/export", json={**q, "title": label, "format": "xlsx"}, headers=headers)
        paths["ad_hoc"] = r
        r = await s.client.post("/api/v1/saved-reports", json={"name": label, **q}, headers=headers)
        assert r.status_code == 200, r.text
        paths["saved_v1"] = await s.client.get(f"/api/v1/reports/saved/{r.json()['id']}/export?format=xlsx", headers=headers)
        for key, definition in [
            ("saved_v2_equivalent", {"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["customer"]}}),
            ("saved_v2_model", {"query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"], "breakdowns": ["customer"]}}),
        ]:
            r = await s.client.post("/api/v1/saved-reports", json={"name": label, "visual": "table", "definition_v2": definition}, headers=headers)
            assert r.status_code == 200, r.text
            eq = r.json()["definition_v2"]["v1_equivalent"]
            resp = await s.client.get(f"/api/v1/reports/saved/{r.json()['id']}/export?format=xlsx", headers=headers)
            paths[f"{key}(v1_equivalent={eq})"] = resp
        for name, resp in paths.items():
            assert resp.status_code == 200, (name, resp.text)
            wb = load_workbook(BytesIO(resp.content))
            cells = [c for sh in wb for row in sh for c in row]
            label_cells = [c for c in cells if c.value == label]
            nums = [c for c in wb["Data"]["B"][1:] if c.value is not None] if wb["Data"].max_column >= 2 else []
            report.append({
                "label": label, "path": name,
                "label_cells": len(label_cells), "label_types": sorted({c.data_type for c in label_cells}),
                "cover_A1": [wb["Cover"]["A1"].value == label, wb["Cover"]["A1"].data_type],
                "any_formula": any(c.data_type == "f" for c in cells) or _xml_has_formula(resp.content),
                "data_header": [c.value for c in wb["Data"][1]],
                "data_B_types": sorted({(type(c.value).__name__, c.data_type) for c in nums}),
            })
    OUT.append({"http": report})
    assert all(r["label_cells"] >= 1 and r["label_types"] == ["s"] and not r["any_formula"] for r in report), report


def teardown_module(module):
    with open(__file__.replace(".py", "_output.json"), "w", encoding="utf-8") as fh:
        json.dump(OUT, fh, indent=1, default=str)

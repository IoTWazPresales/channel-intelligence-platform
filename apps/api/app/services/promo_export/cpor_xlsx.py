"""Legacy promo-plan workbook builder.

The old promotion tables were dropped in 20261011_0032. Case export is
``/api/v1/cpor/cases/{id}/export``. These functions refuse to read the dropped tables.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy.orm import Session

TEMPLATE_CODE = "cpor_v1"
DATA_SHEET = "CPOR_PromoPlan"
HEADER_ROW = 1
FIRST_DATA_ROW = 2


def _build_blank_template_workbook() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = DATA_SHEET
    headers = [
        "Customer_Code",
        "Customer_Name",
        "Channel_Code",
        "Promo_Code",
        "Promo_Name",
        "SKU",
        "Product_Name",
        "Expected_Uplift_Pct",
        "Support_Needed",
        "Stock_Readiness",
        "Volume_Planning",
    ]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=HEADER_ROW, column=col, value=header)
    ws.freeze_panes = "A2"
    return wb


def template_workbook_bytes() -> bytes:
    bio = BytesIO()
    _build_blank_template_workbook().save(bio)
    return bio.getvalue()


def validate_promotion_for_export(session: Session, promotion_id: int) -> tuple[bool, list[str], list[dict[str, Any]]]:
    _ = (session, promotion_id)
    return False, ["Promotion plan exports were removed. Export the case instead."], []


def build_promo_plan_workbook_bytes(
    session: Session,
    promotion_id: int,
    *,
    default_customer_id: int | None = None,
    default_channel_code: str | None = None,
) -> tuple[bytes, str]:
    _ = (session, promotion_id, default_customer_id, default_channel_code)
    raise ValueError("Promotion plan exports were removed. Export the case instead.")

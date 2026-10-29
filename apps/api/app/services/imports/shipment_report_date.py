"""Report date for an ACZA Shipped/Unshipped workbook.

The date is the single ``YYYYMMDD`` token in the file name (``ACZA Shipped Unshipped
20260911.xlsx``, including a suffix such as ``_P2``). Upload time and mail
``received_at`` are not the report date: job 1339 was uploaded on 14 September
and the file is the 11 September book. A name with no token, or more than one,
has no report date (``shipped 2020-2023.xlsx``).
"""

from __future__ import annotations

import re
from datetime import date

_FILE_DATE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def report_date_from_file_name(file_name: str | None) -> date | None:
    matches = list(_FILE_DATE.finditer(file_name or ""))
    if len(matches) != 1:
        return None
    year, month, day = (int(part) for part in matches[0].groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def report_date_for_job(job) -> date | None:
    """Report date for this job under the tenant's rule.

    The default rule is the single YYYYMMDD in the file name. A rule this
    process does not implement yields no date, so the job closes nothing.
    """
    from app.services.commercial_tenant_profile import (
        OPEN_BOOK_REPORT_DATE_FILENAME,
        open_book_report_date_rule,
    )

    tenant_id = str(getattr(job, "tenant_id", None) or "default")
    if open_book_report_date_rule(tenant_id) != OPEN_BOOK_REPORT_DATE_FILENAME:
        return None
    return report_date_from_file_name(getattr(job, "file_name", None))

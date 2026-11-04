"""Store place name from the sell-through source row.

The store code stays ``site_label``. This reads the name the file already stored.
It does not geocode and it does not write the fact.
"""

from __future__ import annotations

import re
from typing import Any

# Dual-header week band after disambiguation, e.g. ``Sales U TY 022.2026``.
_WEEK_BAND_KEY = re.compile(r"(?:^|\s)\d{1,3}[./-]\d{4}$")
_CALENDAR_DAY_KEY = "Calendar Day"
_SITE_NAME_KEY = "Site Name"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def place_name_from_raw(raw: dict | None) -> str | None:
    """Return the place name for one source row, or None when the file has none.

    Named ``Site Name`` wins. A calendar-day file (a ``Calendar Day`` column) uses
    ``col_10``. A week-band file (a ``022.2026``-style column) uses ``col_11``.
    """
    if not isinstance(raw, dict):
        return None
    named = _clean(raw.get(_SITE_NAME_KEY))
    if named:
        return named
    if _CALENDAR_DAY_KEY in raw:
        return _clean(raw.get("col_10"))
    if any(_WEEK_BAND_KEY.search(str(key)) for key in raw):
        return _clean(raw.get("col_11"))
    return None

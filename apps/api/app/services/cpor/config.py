"""CPOR tenant config constants (module-level, same pattern as lineup archive config).

Spec §4: assumed_sellout_currency when sell-out currency_code is blank/0-filled.
Default lookback when no prior CPOR case exists for (customer, product).
"""

from __future__ import annotations

# A2-04 window lives on commercial_tenant_profile (env SUPPORT_NORMS_TRAILING_QUARTERS);
# re-export for existing CPOR imports.
from app.services.commercial_tenant_profile import (
    SUPPORT_NORMS_TRAILING_QUARTERS,
    support_norms_trailing_quarters,
)

# Spec §4 — sell-out currency_code is 0-filled on cip; assume ZAR and flag.
ASSUMED_SELLOUT_CURRENCY = "ZAR"

# Spec §4 — lookback when no prior CPOR case window_end for that product/customer.
DEFAULT_SELLOUT_LOOKBACK_DAYS = 180

# Money storage / fixture display scale (Numeric(18,4) columns; fixtures assert 2dp).
MONEY_QUANTIZE = "0.01"
STORAGE_QUANTIZE = "0.0001"

__all__ = [
    "ASSUMED_SELLOUT_CURRENCY",
    "DEFAULT_SELLOUT_LOOKBACK_DAYS",
    "SUPPORT_NORMS_TRAILING_QUARTERS",
    "support_norms_trailing_quarters",
    "MONEY_QUANTIZE",
    "STORAGE_QUANTIZE",
]

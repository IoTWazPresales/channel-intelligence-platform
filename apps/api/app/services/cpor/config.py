"""CPOR tenant config constants (module-level, same pattern as lineup archive config).

Spec §4: assumed_sellout_currency when sell-out currency_code is blank/0-filled.
Default lookback when no prior CPOR case exists for (customer, product).
"""

from __future__ import annotations

# Spec §4 — sell-out currency_code is 0-filled on cip; assume ZAR and flag.
ASSUMED_SELLOUT_CURRENCY = "ZAR"

# Spec §4 — lookback when no prior CPOR case window_end for that product/customer.
DEFAULT_SELLOUT_LOOKBACK_DAYS = 180

# A2-04 — trailing support norms window (tenant config; default 4 quarters).
SUPPORT_NORMS_TRAILING_QUARTERS = 4

# Money storage / fixture display scale (Numeric(18,4) columns; fixtures assert 2dp).
MONEY_QUANTIZE = "0.01"
STORAGE_QUANTIZE = "0.0001"

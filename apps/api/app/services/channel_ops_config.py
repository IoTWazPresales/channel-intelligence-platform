"""Channel Ops tenant config (module-level constants — same pattern as cpor/config).

A3-03 replenishment v1 is a threshold flag vs weeks-of-cover, not a recommendation engine.
"""

from __future__ import annotations

# A3-03 — flag when 0 < weeks_of_cover < threshold. Default 4 weeks.
REPLENISHMENT_WOC_THRESHOLD_WEEKS = 4.0

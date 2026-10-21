# N-0110 clone proof for 20261014_0037 (2026-10-14)

Clone `cip_n0110` made from `cip` with pg_dump/pg_restore, then dropped.

- source cip: current_database cip, rev 20261014_0036, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col False, position_table False
  admin step as postgres (superuser True): DROP DATABASE IF EXISTS cip_n0110
  admin step as postgres (superuser True): CREATE DATABASE cip_n0110 OWNER cip
- clone before: current_database cip_n0110, rev 20261014_0036, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col False, position_table False
- clone after upgrade: current_database cip_n0110, rev 20261014_0037, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col True, grain_not_null 0, position_table True, positions 0, compared 0
- clone after downgrade: current_database cip_n0110, rev 20261014_0036, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col False, position_table False
- clone after re-upgrade: current_database cip_n0110, rev 20261014_0037, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col True, grain_not_null 0, position_table True, positions 0, compared 0
- clone after recompute: current_database cip_n0110, rev 20261014_0037, fact_rows 1823, fact_units 6159.0000, fact_soh 28812.0000, fact_soh_rows 1420, staging_rows 43472, grain_col True, grain_not_null 0, position_table True, positions 701, compared 314
- fact and staging numbers unchanged through every step: True
- existing rows keep NULL grain: True
  admin step as postgres (superuser True): DROP DATABASE IF EXISTS cip_n0110
- clone dropped; dump removed. CLONE_PROOF PASS

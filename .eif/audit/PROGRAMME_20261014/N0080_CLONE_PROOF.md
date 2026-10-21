# N-0080 clone proof for 20261014_0036 (2026-10-14)

Clone `cip_n0080` made from `cip` with pg_dump/pg_restore, then dropped.

- source cip: rev 20261012_0035, landed_col False, sku_rows 31, sku_cost_sum 17602.0
- clone before: rev 20261012_0035, landed_col False, sku_rows 31, sku_cost_sum 17602.0
- clone after upgrade: rev 20261014_0036, landed_col True, sku_rows 31, sku_cost_sum 17602.0
- clone after downgrade: rev 20261012_0035, landed_col False, sku_rows 31, sku_cost_sum 17602.0
- clone after re-upgrade: rev 20261014_0036, landed_col True, sku_rows 31, sku_cost_sum 17602.0
- clone dropped; dump removed. CLONE_PROOF PASS

cip_test: upgrade, downgrade, upgrade passed (rev 20261014_0036).

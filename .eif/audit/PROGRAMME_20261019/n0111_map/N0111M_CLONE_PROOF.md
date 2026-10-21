# N-0111 mapping slots: clone proof for 20261019_0044 (2026-10-19)

Clone `cip_n0111m` made from `cip` with pg_dump/pg_restore, then dropped.

- cip (source, read only): db cip, rev 20261016_0043, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 0
- clone before: db cip_n0111m, rev 20261016_0043, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 0
  alembic upgrade head on database cip_n0111m as postgres (superuser True)
- clone after upgrade: db cip_n0111m, rev 20261019_0044, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 5, rows_with_new_values 0
  alembic downgrade -1 on database cip_n0111m as postgres (superuser True)
- clone after downgrade: db cip_n0111m, rev 20261016_0043, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 0
  alembic upgrade head on database cip_n0111m as postgres (superuser True)
- clone after upgrade again: db cip_n0111m, rev 20261019_0044, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 5, rows_with_new_values 0
- round trip keeps every count: True
- all five columns present after upgrade: True; none after downgrade: True
- existing rows carry no new value (all NULL): True
- clone cip_n0111m dropped
- cip after (unchanged): db cip, rev 20261016_0043, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 0
- cip unchanged by the clone proof: True
CLONE_PROOF PASS

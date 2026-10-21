# N-0111 mapping slots: apply 20261019_0044 to cip (2026-10-19)

- cip before: db cip, rev 20261016_0043, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 0
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, rev 20261019_0044, staging_rows 46718, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 613, layouts 7, sources 43, new_columns_present 5, rows_with_new_values 0
- cip counts unchanged by 20261019_0044: True; revision now 20261019_0044

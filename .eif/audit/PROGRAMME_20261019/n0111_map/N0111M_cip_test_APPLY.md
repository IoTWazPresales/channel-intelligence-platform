# N-0111 mapping slots: apply 20261019_0044 to cip_test (2026-10-19)

- cip_test before: db cip_test, rev 20261016_0043, staging_rows 0, cst_fact_rows 0, cst_units 0, cst_onhand 0, cst_superseded 0, import_jobs 1956, layouts 0, sources 17, new_columns_present 0
  alembic upgrade head on database cip_test as postgres (superuser True)
- cip_test after: db cip_test, rev 20261019_0044, staging_rows 0, cst_fact_rows 0, cst_units 0, cst_onhand 0, cst_superseded 0, import_jobs 1956, layouts 0, sources 17, new_columns_present 5, rows_with_new_values 0
- cip_test counts unchanged by 20261019_0044: True; revision now 20261019_0044

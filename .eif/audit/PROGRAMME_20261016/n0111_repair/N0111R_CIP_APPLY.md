# N-0111 repair: apply 20261016_0042 to cip
- cip before: db cip, rev 20261016_0041, sellout_rows 35582, sellout_units 178195.8500, returns_rows 3176, inventory_rows 47411, dsi_staging_rows 183463, cst_fact_rows 3197, cst_units 12394.0000, superseded_table False, superseded_rows None
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, rev 20261016_0042, sellout_rows 35582, sellout_units 178195.8500, returns_rows 3176, inventory_rows 47411, dsi_staging_rows 183463, cst_fact_rows 3197, cst_units 12394.0000, superseded_table True, superseded_rows 0
- cip counts unchanged by 20261016_0042: True

# N-0111 layouts: apply 20261016_0043 to cip
- cip before: db cip, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, rev 20261016_0043, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table True, layouts 0, is_hidden_column True, sources_hidden 0
- cip counts unchanged by 20261016_0043: True

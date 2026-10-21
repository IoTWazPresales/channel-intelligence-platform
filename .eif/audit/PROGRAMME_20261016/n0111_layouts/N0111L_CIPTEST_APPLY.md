# N-0111 layouts: apply 20261016_0043 to cip_test
- cip_test before: db cip_test, rev 20261016_0042, cst_fact_rows 0, cst_units 0, cst_onhand 0, cst_superseded 0, import_jobs 1236, sources 17, sellout_rows 67, layout_table False, layouts None, is_hidden_column False, sources_hidden None
  alembic upgrade head on database cip_test as postgres (superuser True)
- cip_test after: db cip_test, rev 20261016_0043, cst_fact_rows 0, cst_units 0, cst_onhand 0, cst_superseded 0, import_jobs 1236, sources 17, sellout_rows 67, layout_table True, layouts 0, is_hidden_column True, sources_hidden 0
- cip_test counts unchanged by 20261016_0043: True

# N-0111 layouts clone proof
- cip (source, read only): db cip, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
- clone before: db cip_n0111l, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
  alembic upgrade head on database cip_n0111l as postgres (superuser True)
- clone after upgrade: db cip_n0111l, rev 20261016_0043, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table True, layouts 0, is_hidden_column True, sources_hidden 0
  alembic downgrade -1 on database cip_n0111l as postgres (superuser True)
- clone after downgrade: db cip_n0111l, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
  alembic upgrade head on database cip_n0111l as postgres (superuser True)
- clone after upgrade again: db cip_n0111l, rev 20261016_0043, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table True, layouts 0, is_hidden_column True, sources_hidden 0
- round trip keeps every count: True

## Source migration on the clone
### dry run (writes nothing)
- clone after dry run: db cip_n0111l, rev 20261016_0043, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table True, layouts 0, is_hidden_column True, sources_hidden 0
- dry run wrote nothing: True
### apply (and a second apply)
- clone after the migration: db cip_n0111l, rev 20261016_0043, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table True, layouts 7, is_hidden_column True, sources_hidden 26
- sell-through facts, jobs and sources unchanged by the migration: True
  alembic downgrade -1 on database cip_n0111l as postgres (superuser True)
- clone after downgrade with layouts present (the layout table and hide flag are dropped): db cip_n0111l, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
- downgrade with layouts present keeps every fact, job and source: True
- clone cip_n0111l dropped
- cip after (unchanged): db cip, rev 20261016_0042, cst_fact_rows 3197, cst_units 12394.0000, cst_onhand 30832.0000, cst_superseded 390, import_jobs 610, sources 43, sellout_rows 35582, layout_table False, layouts None, is_hidden_column False, sources_hidden None
- cip unchanged by the clone proof: True

# N-0096 apply 20261015_0040 to cip
- cip before: db cip, rev 20261015_0039, stock_position_rows 701, stock_position_compared 314, superseded_rows 390, superseded_units 1124.0000, app_role cip, app_sees_stock_position 701, app_sees_superseded 390
- cip before: policy definitions
    customer_stock_position DELETE: using='cip_product_id_editable((product_id)::bigint)' with_check=None
    customer_stock_position INSERT: using=None with_check='cip_product_id_editable((product_id)::bigint)'
    customer_stock_position SELECT: using='cip_product_id_visible((product_id)::bigint)' with_check=None
    customer_stock_position UPDATE: using='cip_product_id_editable((product_id)::bigint)' with_check='cip_product_id_editable((product_id)::bigint)'
    fact_customer_sellthrough_superseded INSERT: using=None with_check='cip_product_id_editable((product_id)::bigint)'
    fact_customer_sellthrough_superseded SELECT: using='cip_product_id_visible((product_id)::bigint)' with_check=None
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, rev 20261015_0040, stock_position_rows 701, stock_position_compared 314, superseded_rows 390, superseded_units 1124.0000, app_role cip, app_sees_stock_position 701, app_sees_superseded 390
- cip after: policy definitions
    customer_stock_position DELETE: using="((product_id IS NULL) OR (COALESCE(current_setting('cip.editable_product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_editable((p.product_line)::text))))" with_check=None
    customer_stock_position INSERT: using=None with_check="((product_id IS NULL) OR (COALESCE(current_setting('cip.editable_product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_editable((p.product_line)::text))))"
    customer_stock_position SELECT: using="((product_id IS NULL) OR (COALESCE(current_setting('cip.product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_visible((p.product_line)::text))))" with_check=None
    customer_stock_position UPDATE: using="((product_id IS NULL) OR (COALESCE(current_setting('cip.editable_product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_editable((p.product_line)::text))))" with_check="((product_id IS NULL) OR (COALESCE(current_setting('cip.editable_product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_editable((p.product_line)::text))))"
    fact_customer_sellthrough_superseded INSERT: using=None with_check="((product_id IS NULL) OR (COALESCE(current_setting('cip.editable_product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_editable((p.product_line)::text))))"
    fact_customer_sellthrough_superseded SELECT: using="((product_id IS NULL) OR (COALESCE(current_setting('cip.product_lines'::text, true), ''::text) = ANY (ARRAY[''::text, '*'::text])) OR ((product_id)::bigint IN ( SELECT p.id\n   FROM dim_product p\n  WHERE cip_product_line_visible((p.product_line)::text))))" with_check=None

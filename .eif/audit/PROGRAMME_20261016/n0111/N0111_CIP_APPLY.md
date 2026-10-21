# N-0111 apply 20261016_0041 to cip
- cip before: db cip, rev 20261015_0040, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying])::text[])))
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, rev 20261016_0041, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 1, figures_col 1, on_hand_nullable YES, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying, 'no_on_hand'::character varying, 'chain_restart'::character varying])::text[])))
- cip counts unchanged by 20261016_0041: True

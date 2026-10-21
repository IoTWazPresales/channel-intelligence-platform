# N-0083 apply to cip, 20261015_0039
- cip before: db cip, user cip, rev 20261015_0038, cases 311, booked 308, has_booked_cols 0, owner postgres, can_select False, can_insert False, can_update False, seq_usage False, rate_rows denied: permission denied for table fx_daily_rate
  alembic upgrade head on database cip as postgres (superuser True)
- cip after: db cip, user cip, rev 20261015_0039, cases 311, booked 308, has_booked_cols 3, owner postgres, can_select True, can_insert True, can_update True, seq_usage True, rate_rows 0
- cip after: app role writes fx_daily_rate (rolled back) (database cip as cip): insert ok

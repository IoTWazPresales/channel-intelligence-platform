# N-0083 clone proof, 20261015_0039
clone cip_n0083 made from cip
- clone before: db cip_n0083, user cip, rev 20261015_0038, cases 311, booked 308, has_booked_cols 0, owner postgres, can_select False, can_insert False, can_update False, seq_usage False, rate_rows denied: permission denied for table fx_daily_rate
- clone before: app role writes fx_daily_rate (database cip_n0083 as cip): denied: permission denied for table fx_daily_rate
  alembic upgrade head on database cip_n0083 as postgres (superuser True)
- clone after upgrade: db cip_n0083, user cip, rev 20261015_0039, cases 311, booked 308, has_booked_cols 3, owner postgres, can_select True, can_insert True, can_update True, seq_usage True, rate_rows 0
- clone after upgrade: app role writes fx_daily_rate (database cip_n0083 as cip): insert ok
  alembic downgrade -1 on database cip_n0083 as postgres (superuser True)
- clone after downgrade: db cip_n0083, user cip, rev 20261015_0038, cases 311, booked 308, has_booked_cols 0, owner postgres, can_select False, can_insert False, can_update False, seq_usage False, rate_rows denied: permission denied for table fx_daily_rate
  alembic upgrade head on database cip_n0083 as postgres (superuser True)
- clone after second upgrade: db cip_n0083, user cip, rev 20261015_0039, cases 311, booked 308, has_booked_cols 3, owner postgres, can_select True, can_insert True, can_update True, seq_usage True, rate_rows 0
clone dropped

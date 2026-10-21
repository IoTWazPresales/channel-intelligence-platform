# N-0083 baseline (before the change, HEAD `51bdc160`)

Observed in code and on `cip` (alembic `20261015_0038`):

- `fx_daily_rate` and its id sequence are owned by `postgres`. Role `cip` has no privilege on them, not even SELECT.
  `ensure_rate_for_date` swallowed the failed insert (`fx persist failed`) and still returned the fetched rate. The table had 0 rows on `cip`.
- `apply_create_fx` booked today's fetched rate at create, whatever the case dates were. `book_on_approve` took override, then the
  create-time proposed rate, then the existing snapshot. It never read the table for the case's date.
- An approval override was not audited beyond the approve event carrying the typed number. `PATCH` of `roe_snapshot` on a booked draft
  overwrote it with no reason and no old value. A reapproval (`needs_reapproval`) could re-book a different rate.
- Proposed (`fx_proposed_*`) and booked (`roe_snapshot`, `fx_declared_*`) are already separate columns. That is kept.
- `fx_mode` defaults to `booked` at create and floating is selectable. That is kept.
- The brief's "Settlement blocked" signal counted cases with **no rate** (`case_missing_roe`) and called them FX blocked.
- `cpor_case` on `cip`: 311 cases, 308 with a rate; 2 open cases have a rate and no mode.

# Step 12 - needs-a-look data fix applied to cip (2 November 2026)

Branch `feat/ns-2-brief-nav-collapse`. No product code changed. No restart, no migration, no database dropped.

## Step 1 - full API suite on cip_test
`DATABASE_URL` / `DATABASE_URL_SYNC` pointed at `cip_test`, run from `apps/api` with the project venv:

**3,547 passed, 24 skipped, 0 failed** (29m34s). Log: `apps/api/pytest-cip-test-step1.log`.

The 24 skips are opt-in or environment gated, none caused by our changes: browser render opt-ins (3), tests needing `cip` or real cip data (4), tests needing `ALLOW_TESTS_ON_DEV_DB=1` (3), tests needing migration `20260608_0048` (6), missing `cip_bulk_smoke` clone (2), fixtures absent on this database (4), remote Supabase E2E, session-auth mode.

Note: two earlier attempts ran nothing (system Python has no `sqlalchemy`; the venv at `apps/api/.venv` is required). Only the third run counts.

## Step 2a - dry run on cip (job 1697)
`merge_shipped_fact_identity_twins.py --retire-orphan-open-rows --job 1697 --expect-db cip`: 9 rows, 921 units, 9 with a replacement. Replacement quantities were read separately (read-only query), because the script does not print them.

| orphan fact | order no | item | qty | replaced by | replacement qty |
|---|---|---|---|---|---|
| 148768 | 151126081010672 | 90NX09J2-M00RW0 | 21 | 170755 | 21 |
| 148777 | 151126071008977 | 90NX0AL1-M004B0 | 128 | 170759 | 128 |
| 148780 | 151126081014465 | 90NX0861-M01X30 | 36 | 170760 | 36 |
| 148785 | 151126081013514 | 90NX0AM2-M00640 | 120 | 170761 | 120 |
| 148786 | 151126081013513 | 90NX09J2-M00RW0 | 10 | 170813 | 10 |
| 148801 | 151126081010739 | 90NX09J2-M00FP0 | 21 | 170814 | 21 |
| 157127 | 151126091006582 | 90NX08N1-M03CC0 | 125 | 170754 | 125 |
| 163464 | 151126091007566 | 90NX08F1-M01520 | 300 | 170815 | 300 |
| 163465 | 151126101003140 | 90NX0AM2-M00N10 | 160 | 170816 | 160 |

All 9 replacements are in job 1697 and match quantity exactly (921 units total).

## Step 2b - apply
Same command with `--apply --expect-db cip`, as the table owner (postgres login via `PG_OWNER`, not printed). Result: `retired: {superseded: 9, disappeared: 0}`.

Audit event: **id 26**, action `shipped_fact_orphan_open_retire`, target import_job 1697, 2026-11-02 14:57 (Africa/Johannesburg), fact ids as in the table above.

## Step 2c - dry run again
`orphaned_open_rows: 0, units: 0.0, rows: []`.

## Step 2d - needs-a-look on cip (`cip_water_check.py`, read-only, in-process)

| | lines | units |
|---|---|---|
| Before | 15 | 1,067 |
| After | 9 | 731 |

After matches the expected 9 / 731. `/shipping/lines?cohort=needs_look` returns 9 rows; the brief attention row reads "9 shipped-sheet lines still open". Since-date 2026-07-21; on-board moved 2026-10-11 to 2026-10-18 (unchanged).

## Step 2f
Nothing restarted. The figures were read from the app in-process against cip, which showed the new numbers without a restart. Not checked: whether the long-running API process serves the new figures (it was not queried).

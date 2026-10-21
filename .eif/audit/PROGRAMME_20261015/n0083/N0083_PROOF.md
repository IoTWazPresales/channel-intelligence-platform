# N-0083 proof: FX rate table and ROE governance

Product commit `5104f59c`. Migration `20261015_0039`.

## Criterion 1: the FX poller writes `fx_daily_rate` on cip

- Cause: `20260905_0021` created the table and sequence under the migration role (`postgres`) with no grant to the app role `cip`.
- Fix: `20261015_0039` grants SELECT, INSERT, UPDATE on `fx_daily_rate` and USAGE, SELECT on `fx_daily_rate_id_seq` to `cip`.
- Clone proof (`cip_n0083`, made from `cip`, dropped after; `N0083_CLONE_PROOF.md`): before, the app role was denied insert and select. After upgrade the
  insert worked. Downgrade restored the denial and removed the three columns. The second upgrade matched the first. Cases 311 and booked 308 on every step.
- Applied to `cip` as the migration role (`N0083_CIP_APPLY.md`): before, denied; after, SELECT/INSERT/UPDATE and sequence USAGE true; cases 311, booked 308 unchanged.
- API restarted through the supervisor. The startup poll stored: `fx_daily_rate` on `cip` = USDZAR 16.470000 for 2026-10-14, source `frankfurter.ecb`,
  fetched 2026-10-15 09:43:23, not fallback. Rows: 0 before, 1 after.
- A fetched rate that the table refuses now logs an error and returns `persisted: false` (before it was a warning and invisible).

## Criterion 2: a case ROE is the stored rate for its date, or an explicit audited override

- The case's own date is its window start, or today when the window has not started. `rate_for_case_date` uses the stored row for that date (or the last row up to 4 days before,
  for a weekend or holiday), and fetches and stores one only when none is stored. A fetch failure gives no rate. No older row is substituted.
- Create books that rate as provisional. Approval books it again from the same rule and fixes it. A rate the operator typed that differs from the stored rate is a manual
  override: approval needs `fx_rate_reason` (400 without), the proposed columns keep the stored rate, and `cpor_case.fx_booked_source / fx_booked_rate_date / fx_override_reason`
  record how it was chosen. An `fx_booked` case event carries rate, source, rate date, stored rate and reason. A booked draft changed through PATCH needs `fx_override_reason` and writes an `fx_override` event.
- A reapproval keeps the rate; a different one is refused (409).
- Warren's settled rules: booked is the default mode, floating stays; proposed and booked are separate columns; FX blocked now means the mode is missing, not the rate
  (the brief signal counts rate-missing cases apart). On `cip` now: 2 open cases with a rate and no mode, 0 with no rate.
- The approve dialog starts empty (stored rate books), asks for a reason when a rate is typed, and the plan states how the booked rate was chosen.

## Criterion 3: checks

- pytest on `cip_test`, touched areas: FX unit and endpoint tests 36, new DB tests 13 (`test_fx_case_rate_db.py`), brief signals 3. Wider cpor/settle/brief set: 210 passed.
  Failures in that set are not FX: 4 in `test_promo_plan_builder.py` (`FakeSession` lacks `begin_nested`, from `budget_ledger.used_usd`, N-0079), 2 in `test_rbac_n0038_cpor_roles.py`
  (the `approval-link` route, N-0082), and `test_cpor_settle_confirm_clone.py` errors because database `cip_ns4_settle_clone` no longer exists (it also leaves settings pointed at it for later modules in the same run).
- vitest `promotions-funding`: 27 passed, 1 failed (`PaymentEvidenceOverlay.test.tsx` looks for "historical source attestation", text no source emits; not touched).
- web `tsc --noEmit` exit 0. `next lint` on the 3 changed web files: no warnings or errors. No Python linter available.
- Web rebuilt (`Ac-dqUkOPp_UMSxKPp8u1`); API and web restarted through the supervisor; `/health` 200, `/login` 200.

## Limits

- Same session, same model. N-0099 does the second look.
- The approve dialog and the plan basis line were not rendered in a browser (sign-in).
- Existing booked cases on `cip` have no booked source (shown as "carried over with the case"); nothing was backfilled.
- The public tunnel is blocked by the network (port 7844), as before; local API and web are up.

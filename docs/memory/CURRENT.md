# CURRENT state

**Last updated:** 2026-08-20 (shipping-mailer on main; API tests pin `CIP_AUTH_MODE=stub`)

**Branch:** `main`

**Last content pin:** `b5e92d1` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

## On main

- Merged `feat/shipping-mailer-recipients` at `b5e92d1` (pushed). Code head is `0019`; cip already had `0019`.
- **API test pin (not a fix):** `apps/api/tests/conftest.py` `setdefault("CIP_AUTH_MODE", "stub")` so the suite does not inherit `.env` session. Do not edit `.env` or `config.py` default. Explicit process `CIP_AUTH_MODE=session` still wins (R1d).
- **CPOR settlement design** (docs only): `docs/CPOR_SETTLEMENT_SPEC.md`. D-057–D-065. BACKLOG-135–140 for §9 gaps.
- BACKLOG-144: `cip_test` lacks fixtures for `test_lineup_distributor_as_customer_remediation.py` — leave failing; do not seed blindly.

## Next

Promote `feat/rbac-r1-session-actor` (R1–R1d) to main, then steward + CPOR queue depth on `feat/steward-queue-depth`. Settlement / MAC / line-windows are **not** started. Clone DB `cip_merged_leftover_repair` can still be dropped when convenient; **`cip_test` is real test infra — do not drop.**

**Env:** local Windows. Web `:3000` + API `:8001`.

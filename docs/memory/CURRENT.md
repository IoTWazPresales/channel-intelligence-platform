# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1–R1d merged to main)

**Branch:** `main`

**Last content pin:** `44530a4` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

**Alembic on cip_test:** `20260818_0018` (OWNER cip)

## On main

- **RBAC program CLOSED at R1–R1d.** CPOR writes authenticate; actor from `user["id"]`. 41 non-CPOR header gates → `require_roles(Role.ADMIN)`. Web 401 clears token and routes to `/login`. No Role enum expansion. No `require_roles` on CPOR (R2). BACKLOG-136 / BACKLOG-141 parked; triggers unchanged.
- Merged `feat/shipping-mailer-recipients` at `b5e92d1`. Code + cip head `0019`.
- **API test pin (not a fix):** `apps/api/tests/conftest.py` `setdefault("CIP_AUTH_MODE", "stub")`. Explicit process `CIP_AUTH_MODE=session` still wins (R1d). Do not edit `.env` or `config.py` default.
- **CPOR settlement design** (docs only): `docs/CPOR_SETTLEMENT_SPEC.md`. D-057–D-065. BACKLOG-135–140 for §9 gaps.
- BACKLOG-144: `cip_test` lacks fixtures for lineup distributor-as-customer remediation tests.

## Next

Steward + CPOR queue depth on `feat/steward-queue-depth` (read-only against cip). Then settlement / MAC / line-windows from the spec + D-057–D-065; pick a BACKLOG-135–140 TRIGGER rather than re-deriving. **`cip_test` is real test infra — do not drop.** Clone DB `cip_merged_leftover_repair` can still be dropped when convenient.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.

# CURRENT state

**Last updated:** 2026-08-21 (promote provisionals Phase A dry-run)

**Branch:** `feat/promote-provisionals-run`

**Last content pin:** `0a649df` (main at branch-off) — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

**Alembic on cip_test:** `20260818_0018` (OWNER cip)

## On this branch

- Steward mint run, not a build. No migration, no model/service change.
- **Phase A complete (dry-run).** `current_database()=cip`. Open TMP **4795 / 25** (delta 0 vs queue-depth). All **4795** customers and **25** distributors `ready`. Zero ineligible. Intra-batch reserved-set collisions: **0**. Sequential-confirm projection: `CUST-000001`..`CUST-004795`, `DIST-000001`..`DIST-000025`. Both `next_seq` still **1**. All **308** TMP-coded `cpor_case` rows would be covered.
- Shipped bulk cap is **500**; dry_run chunks remint from seq 1 (does not advance). Phase B confirm chunks would consume seq sequentially.
- **Phase B not started** — waits for Warren’s explicit word.
- BACKLOG-145: recode-after-promote has no path (customer and distributor).
- **RBAC program CLOSED at R1–R1d** (on main, inherited).

## Next

Warren reads Phase A and says whether to run Phase B (`dry_run=false`, customers then distributors). Do not start B without that word. After B: re-run queue-depth; expected open TMP near 0 and the 308 gone.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.

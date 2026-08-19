# CURRENT state

**Last updated:** 2026-08-19 (Unit 1 resolver guard)

**Branch:** `fix/merged-customer-resolver-guard`

**Last content pin:** `2b2e552` (main at branch start) — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On this branch

- **Unit 1 (committed separately from repair):** every path that returns a `dim_customer.id` (and the same gap on `dim_distributor`) either follows `merged_into_*` to the surviving id or excludes merged rows (reuse / pickers / filter dropdowns). Canonical helper: `app/services/merge_redirect.py`. No migrations. No promote / mint.

- **Unit 2 (not started until Unit 1 is committed):** leftover FK repair via `repoint_customer_footprint_full`. Expect 9 losers / 3,266 rows; clone first, then cip.

## Last recorded test snapshot

`pytest tests/test_merge_redirect.py tests/test_lineup_customer_alias_resolution.py tests/test_source_token_alias_conflicts.py tests/test_dsi_customer_alias_key_resolution.py tests/test_dsi_customer_sim_name_resolution.py tests/test_open_channel_absorb.py` **31 passed**. No migration.

## Next

1. Unit 2 leftover preview (expect 9 / 3266). STOP if drift.
2. Clone repair, then cip. Compuspeed loser 1152 flagged separately.
3. Do not promote or mint customers.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.

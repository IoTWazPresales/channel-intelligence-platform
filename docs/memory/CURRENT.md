# CURRENT state

**Last updated:** 2026-08-19 (Unit 2 leftover repair on cip)

**Branch:** `fix/merged-customer-resolver-guard`

**Last content pin:** `3372915` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On this branch

- **Unit 1** `fc14962`: resolver guard. Follow `merged_into_*` on customer/distributor resolvers; exclude merged from reuse/pickers. Canonical `merge_redirect.py`.
- **Unit 2:** leftover FK repair via `repoint_customer_footprint_full`. Preview 9 losers / 3266 rows matched audit. Clone `cip_merged_leftover_repair` PASS then cip PASS. Leftover query across 250 merged losers = **0**. Compuspeed loser **1152** (10 rows onto OPEN_CHANNEL) flagged as the unexplained pre-absorb case. No migrations. No promote / mint.

## Last recorded test snapshot

Unit 1: `pytest tests/test_merge_redirect.py tests/test_lineup_customer_alias_resolution.py tests/test_source_token_alias_conflicts.py tests/test_dsi_customer_alias_key_resolution.py tests/test_dsi_customer_sim_name_resolution.py tests/test_open_channel_absorb.py` **31 passed**.

Clone then cip leftover repair: leftover_rows_after **0**. Esquire 788: cases 0→18, lineup 0→2, CST 0→0. Amazon 299: cases 0→15, lineup 21→260, CST 0→31.

## Next

Theme complete for this branch (guard + repair). Do not promote to main unless asked. Clone DB `cip_merged_leftover_repair` can be dropped when convenient.

**Env:** local Windows. Web `:3000` + API `:8001`. Clone create terminated cip backends — restart API/web if they dropped.

# CURRENT state

**Last updated:** 2026-08-20 (merged resolver-guard to main)

**Branch:** `main`

**Last content pin:** `57528c5` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On main

- Merged `fix/merged-customer-resolver-guard` at `57528c5`. No open PR.
- **Unit 1** `fc14962`: follow `merged_into_*` on customer/distributor resolvers; exclude merged from reuse/pickers. Canonical `merge_redirect.py`.
- **Unit 2** `3372915`: leftover FK repair via `repoint_customer_footprint_full`. cip leftover=0. Compuspeed loser **1152** flagged. No migrations. No promote / mint.
- **`1aaeef1`:** missing `merged_into_*` attribute = not-merged. Resolver instance reads go through the helper.

## Last recorded test snapshot

Shipment: `test_score_shipment_distributor_display_hint_maps_unique_dim_name` + `test_plan_shipment_historical_corroborated_ready` passed; `test_missing_merged_into_attr_is_not_merged` passed.

Web `admin/customers/page.test.tsx`: 14 passed this run (drawer test 3259ms). Prior full-suite 5000ms timeout is a flake — `apps/web` unchanged vs main; not fixed here.

Clone then cip leftover repair: leftover_rows_after **0**. Esquire 788: cases 0→18, lineup 0→2, CST 0→0. Amazon 299: cases 0→15, lineup 21→260, CST 0→31.

## Next

BACKLOG-133 (zero leftover FKs to merged ids on import completion) and BACKLOG-134 (no `customer_source_token_alias` pointing at a merged id). Clone DB `cip_merged_leftover_repair` can be dropped when convenient.

**Env:** local Windows. Web `:3000` + API `:8001`.

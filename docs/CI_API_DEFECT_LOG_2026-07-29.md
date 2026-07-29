# CI API defect log — 2026-07-29 (P0 Option B)

**Source run:** https://github.com/IoTWazPresales/channel-intelligence-platform/actions/runs/30456826170  
**Branch:** `fix/ci-pnpm-gate` @ `1fb5a69`  
**DB:** ephemeral `cip_test` (Postgres 16 service). `ALLOW_TESTS_ON_DEV_DB` unset.  
**Non-goal this unit:** fixing failing tests — record only.

## Pipeline proven

| Step | Result |
|------|--------|
| pnpm/action-setup (no version clash) | Pass |
| Create `cip_test` | Pass |
| Resolved `DATABASE_URL` / `DATABASE_URL_SYNC` / `DATABASE_URL_SYNC_MIGRATE` → `cip_test` | Pass |
| Alembic fresh path (`upgrade 20260412_0001` + `stamp head` + system reference bootstrap) | Pass |
| `pnpm test:api` | Ran end-to-end |

## Suite totals

**79 failed, 1550 passed, 27 skipped, 30 errors** in ~30s.

## Defect classes (do not fix in this unit)

1. **Hard-coded `current_database() == "cip"`** — several tests refuse disposable DBs (e.g. `test_shipping_commercial_kpis.py`, `test_commercial_planner_api.py`, `test_purchase_order.py`, observation tests). Against `cip_test` they assert-fail by design.
2. **`DimProduct(..., channel_id=...)` TypeError** — large ERROR cluster in `test_distributor_sales_inventory_import.py` (fixture/model drift vs current `DimProduct`).
3. **AI resolver / shipment SimpleNamespace missing `pod_date`** — `test_ai_resolver_integration.py`.
4. **Backfill shipment customer PO asserts `None`** — `test_backfill_shipment_customer_po.py`.
5. **Missing disposable DBs in CI** — `cip_bulk_smoke` not created (`test_lineup_bulk_backfill_apply_integration.py`).
6. **Misc** — event-loop / relation-name / scaffold failures (see artifact `ci-api-pytest.txt` on the Actions run).

Full pytest capture: Actions artifact `ci-api-defect-log` on the run above (also mirrored under `.tmp/ci-defect/` locally during the P0 session).

## Follow-up TRIGGER

Batch-fix the classes above when making CI green is prioritized — **not** inline during P0 load/hygiene. Required GitHub status check remains BACKLOG-**087** (Pro purchased).

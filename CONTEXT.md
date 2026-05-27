# Channel Intelligence Platform — Current Context

## Branch
`feature/dsi-phase-0-foundations` — from `main` @ `7561935` (async DSI apply merged)

## Alembic Head
`20260518_0040` — written on branch; **not** upgraded on `cip` (Warren approval pending). Smoke-verified on `cip_alembic_smoke` only.

---

## Latest work (May 2026) — DSI Phase 0 foundations (in progress on branch)

| Area | What changed |
|------|----------------|
| **Migrations 0038–0040** | Sell-out day grain + `invoice_no` (`''` sentinel); `fact_returns`; inventory `source_key` + reconciliation columns |
| **Fact apply** | Positive qty → `fact_sales_sellout`; negative → `fact_returns` (abs qty); zero skipped; hashed `dsi-sellout:` / `dsi-return:` keys |
| **Post-validate** | Historical workflow enqueues `dsi_resolution_plan_apply` via detached thread/Celery (not `asyncio.run` in pipeline) |
| **UI** | Historical mode label: auto-applies ready candidates after validate |

### E2E (May 2026, local stack)
- Services: `scripts/restart-dev.ps1` — Redis PONG, API `/health`, web `:3000` OK
- Scenarios 1–3: `scripts/e2e_dsi_phase0.py` + API/DB verification PASS on `cip` @ head `20260518_0040`
- Activity bell: `/api/v1/imports/background-tasks` shows `dsi_pipeline` during validate; historical job enqueues `dsi_post_validate_auto_apply` when ready candidates exist
- Focused pytest (7 Phase 0 tests): PASS with `ALLOW_TESTS_ON_DEV_DB=1`

### Next
- Merge `feature/dsi-phase-0-foundations` after review

---

## Prior work (May 2026) — DSI steward scale + product shipment tie-break

### Shipped on feature branch (`ca4ca57`)
| Area | What changed |
|------|----------------|
| **P0 async apply** | `POST .../dsi-resolution-plan/apply-async` → Celery `imports.dsi_resolution_plan_apply`; poll `.../dsi-steward-bulk-task/{task_id}`; activity bell kind `dsi_resolution_plan_apply` |
| **Apply perf** | Product resolution index loaded **once** per task; chunks of 25 candidates; sync `/apply` capped at 50 ids |
| **409 lock** | `dsi_steward_task_dispatch.py` blocks apply when pipeline or `dsi_bulk_task` active |
| **P1 product tie-break** | `dsi_product_shipment_tiebreak.py` — uses `shipment_distinct_product_ids` + `dominant_evidence_month` on candidate context (set on **next revalidate**) |
| **P1 plan labels** | `suggested_target_label` on plan rows (customer/distributor/product names) |
| **P1/P2 UX** | Single **Review…** row action; plan column shows target label; corroboration chip → **Shipment lines found** vs tie-break; resolution panel **one scroll parent** |

### Not changed
- Shipment evidence import module (read-only corroboration only)
- DSI eligibility / corroboration tier order
- Duplicate detection logic

### Job 733 note
- Existing candidates lack new context fields until **revalidate**. Tie-break at plan time uses stored ids when present; else live `_shipment_disambiguate_product_id`.
- Async apply needs **Redis + worker** (or `CIP_DEV_CELERY_DISPATCH=in_process_thread` when Celery enqueue fails). Stale `dsi_bulk_task` in metadata blocks sync apply until cleared or task completes.

### Validation run
- API: 57 tests (`test_dsi_resolution_plan`, bulk steward, tiebreak)
- Web: 39 tests (`import-steward` features)
- API smoke: `apply-async` 202 + 409 lock; sync apply 1 customer ~5s
- Browser E2E job 733: blocked by Next.js dev overlay on imports grid (manual open job still OK)

### Next
- Merge feature branch after review
- Revalidate job 733 to populate `shipment_distinct_product_ids` / `dominant_evidence_month` on product candidates
- Optional: clear stale `dsi_bulk_task` when Celery task orphaned (PENDING + no worker)

---

## Prior work (on `main`)
- Root-identity duplicate scorer (`0503aaf`)
- Steward same-entity UX, cluster map (`c774616`)

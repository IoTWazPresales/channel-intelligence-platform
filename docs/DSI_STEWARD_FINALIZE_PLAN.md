# DSI steward finalize plan (duplicates + UX)

**Status:** Implementing (hub/branch inventory deferred).  
**Scope:** Close duplicate/steward slice; no migrations; no Phase 2 clusters; no branch SOH.

---

## Goals

1. Reduce false-positive duplicate hints (NRC vs NGR class).
2. Inline duplicate peer compare without drawer scroll / candidate swap.
3. Hint when customer token matches a `dim_distributor` name (inter-disti counterparty).
4. Document steward policy + later backlog in memory palace.
5. Unit tests only — **never run pytest against `cip`**.

---

## Files to change

| File | Change |
|------|--------|
| `apps/api/app/services/imports/dsi_customer_name_normalization.py` | Add single-token flip suppression in `dsi_duplicate_similarity_score`. |
| `apps/api/app/services/imports/dsi_customer_intelligence.py` | Add `annotate_dsi_customer_distributor_name_collisions(agg, distributors)`. |
| `apps/api/app/services/imports/distributor_sales_inventory.py` | Call collision annotate after duplicate annotate; persist `distributor_master_collision` on candidate `context`. |
| `apps/api/tests/test_dsi_duplicate_detection_cascade.py` | Cases: NRC/NGR suppressed; Cloud IT/its still flagged. |
| `apps/api/tests/test_dsi_distributor_name_collision.py` | New — collision hint on agg (no DB). |
| `apps/web/.../dsi-mapping-steward-panel.tsx` | Inline peer expand; inter-disti alert from context. |
| `apps/web/.../DsiCandidateStewardDrawer.tsx` | Pass `resolvePeerCandidate` instead of swap callback. |
| `apps/web/.../DsiImportJobResolutionSection.tsx` | Wire `resolvePeerCandidate`; remove peer swap. |
| `apps/web/.../dsiStewardCandidateFilterLogic.ts` | Optional helper to read collision from context (if needed). |
| `CONTEXT.md` | Finalize done + **scoped later** backlog (Phase 2 clusters, hub/branch, web enrichment). |
| `docs/DSI_STEWARD_OPERATIONS.md` | Short steward runbook (duplicates, inter-disti, region vs branch). |

---

## Non-regression guarantees

- Existing duplicate cascade tests (Aeonic/Benric) unchanged.
- `test_dsi_job_progress` / revalidate async behaviour untouched.
- Steward duplicate-review API + same/different entity unchanged.
- Region evidence / duplicate logic stay independent (no region-based merge/split).
- Shipment steward panel untouched.

---

## Deferred (explicitly out of scope)

- Phase 2 duplicate clusters (one provisional + map siblings).
- Distributor hub/branch SOH (`distributor_location` on facts, transfer parsing).
- Web/registry enrichment for duplicate decisions.
- Proxy timeout changes.

---

## Validation

```bash
cd apps/api
.venv/Scripts/python.exe -m pytest tests/test_dsi_duplicate_detection_cascade.py tests/test_dsi_distributor_name_collision.py tests/test_dsi_duplicate_review.py -q
```

No `ALLOW_TESTS_ON_DEV_DB`; no tests against `cip`.

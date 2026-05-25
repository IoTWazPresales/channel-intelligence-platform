# Channel Intelligence Platform — Current Context

## Branch
`main` — ahead of `origin/main` (not pushed unless user asks)

## Recent commits (DSI steward / duplicates)
| Commit | Summary |
|--------|---------|
| `c774616` | **Shipped:** Phase A/B same-entity dialog, bulk customer search, Region/Channel columns; extended duplicate hints (prefix stem, shared-label, source_customer_similar); plan `sibling_mapping_hint`; cluster same-entity API + UI |
| `afb682f` | Sticky steward, cluster/suffix display (info only), pipeline timestamps |
| `26d38e8` | BCS/RBS short-acronym guards |

## Alembic Head
`20260517_0037` — no migration for duplicate work

---

## HANDOVER — new chat should start here (May 2026)

### Goal of the workstream
Finish DSI customer duplicate detection + steward UX so obvious pairs (e.g. **Adriane** + t/a tail) get **review-required hints**, steward can **Same entity** / **Different entity** / **cluster map**, and plan suggests siblings — **without** auto-creating `dim_customer` or weakening BCS/TB guards.

User approved full plan (0 + A/B + Phase 1 + revalidate + Phase 2 + Phase 3). **Code is committed** (`c774616`). **E2E on job 733 is incomplete** due to revalidate crash.

### What is implemented (code — do not re-implement)
1. **Detection (validate-time only)** — `annotate_dsi_customer_candidate_duplicates` in `dsi_customer_intelligence.py`:
   - `dealer_group_prefix_stem`, `dealer_group_shared_label_different_counterparty`, `source_customer_similar`
   - BCS/RBS/TB guards unchanged in `dsi_customer_name_normalization.py`
2. **Steward UX** — `DsiDuplicateSameEntityDialog`, `DsiCustomerSearchFields`, bulk map search, Region/Channel grid cols
3. **Plan** — `sibling_mapping_hint` via `build_job_customer_sibling_index` in plan context
4. **Cluster** — `POST /api/v1/mappings/import-jobs/{job_id}/duplicate-review/cluster-same-entity`; UI **Map cluster to one customer…** when unresolved cluster on page

### Job 733 baseline (before revalidate completed)
- **4511** open customer candidates; **~4494** needs work (mostly provisional plan)
- **`possible_duplicates_only=1` → total 16** (old hints only; pre-new-bases)
- **`duplicate_unresolved_only=1` → total 0** (all 16 pairs already had `duplicate_review`, mostly `different_entity`)
- **Adriane** (`adriane investments (pty) ltd` vs `adriane investments (pty)ltd a/t klinsta`): **`possible_duplicate_of` empty** until revalidate finishes with new code
- Example reviewed pair: `aeon computer technologies` ↔ `aeon solutions (pty) ltd` — `dealer_group_similar`, decision `different_entity`

### Revalidate — COMPLETE (May 2026 session)
- **Task:** `083bb3f0-191f-46d2-884b-7e0ff1c74522` finished ~09:36 local; `dsi-progress`: `status=complete`, `phase=complete`
- **Post-revalidate counts:** `possible_duplicates_only=53` (was 16); `duplicate_unresolved_only=37` (was 0)
- **New `match_basis` in samples:** `dealer_group_prefix_stem`, `dealer_group_similar`, `source_customer_similar`
- **BCS/RBS/TB:** no false-positive hints in duplicate set (guard OK)
- **Adriane pair:** still **no** hints — `dominant_distributor_id` 66 vs 58; `_duplicate_distributor_scope_allows_compare` requires overlapping sell-out distributor IDs (by design, not stem bug)
- **Browser E2E (job 733):** Duplicate review needed grid; Region (file) column visible; steward on Afrika Tikkun cluster shows **Map cluster (2 tokens)**, **Same entity** dialog (search + provisional radios), **Compare**, **Different entity** — all open OK (cancelled without commit)
- **UX note:** `building_candidates` at 100% can sit ~10–15 min with no new phase until persist finishes; bell/`background-tasks` clears when done

### E2E verification checklist (after revalidate complete)
| # | Check | Pass criteria |
|---|--------|----------------|
| 1 | `possible_duplicates_only=1` count | **>> 16** (exact TBD); sample rows show new `match_basis` values |
| 2 | Adriane pair | Both keys have hint; expect `dealer_group_prefix_stem` |
| 3 | BCS/RBS, TB Computers/TB Solutions | Still **no** hints |
| 4 | Unresolved duplicates | `duplicate_unresolved_only=1` > 0 for steward UI tests |
| 5 | Steward drawer | **Same entity (map both)** dialog: search + chips + provisional name |
| 6 | Cluster | 2+ linked tokens on **same page**, unresolved → **Map cluster…** works |
| 7 | Plan sibling | Map token A → customer X; plan for token B (same DG) shows `sibling_mapping_hint` |
| 8 | Region/Channel columns | Visible in customer grid |

**API quick checks (PowerShell-safe):**
```text
GET http://localhost:3000/api/v1/mappings/import-jobs/733/distributor-si-candidates?status=open&entity=customer&possible_duplicates_only=1&limit=5
GET ...&q=adriane&limit=5
GET http://localhost:3000/api/v1/imports/jobs/733/dsi-progress
```

### What was tested before crash
- Unit: 63× `test_dsi_duplicate_*`, 15× web steward logic tests (at commit time)
- Browser/API smoke: job 733 UI loads; Possible duplicates filter = 16; Region column visible; steward Compare works; cluster API returns validation errors (route exists)
- **Not completed:** post-revalidate hint counts, Adriane, Same entity / cluster dialogs on unresolved rows

### Risks / watch items for revalidate on 733
- **Runtime & memory:** Full job revalidate + pairwise duplicate annotate over ~4.5k customer buckets can be **heavy** (O(n²) pairs within distributor scope). May stress worker — monitor memory, run off-hours
- **Steward decisions:** Existing `duplicate_review` on 16 rows should **persist**; hints refresh but decisions are not wiped by revalidate (verify if unexpected)
- **Agent testing:** Do **not** block shell poll >2–3 min; use UI progress or `dsi-progress` every 30s with timeout

### Do not change without explicit approval
- DSI eligibility / corroboration / resolution tier order
- Auto-create `dim_customer` from detection
- Alembic migrations
- Lowering global duplicate thresholds

---

## What Is Working (reference)

### DSI duplicate + steward (code on `main`)
- Extended hint bases + contract; steward Phase A/B; cluster API; sibling plan signal
- Phase 1–3 UX (`afb682f`): sticky steward, cluster info alert, pipeline timestamps
- Duplicate review gates; inter-disti hint; async validate UX

### Key paths
| Area | Path |
|------|------|
| Duplicate cascade + stem | `apps/api/app/services/imports/dsi_customer_name_normalization.py` |
| Hint contract | `apps/api/app/services/imports/dsi_duplicate_hint_contract.py`, `apps/web/.../dsiDuplicateHintContract.ts` |
| Annotate + sibling index | `apps/api/app/services/imports/dsi_customer_intelligence.py` |
| Plan sibling | `apps/api/app/services/imports/dsi_plan_build_context.py`, `dsi_resolution_plan.py` |
| Steward + cluster ops | `dsi_steward_candidate_ops.py`, `apps/api/app/api/v1/endpoints/mappings.py` |
| Revalidate endpoint | `POST .../revalidate-distributor-sales-inventory` in `mappings.py` |
| Progress poll | `GET /api/v1/imports/jobs/{id}/dsi-progress` |

### Tests (no DB)
`.\.venv\Scripts\python.exe -m pytest tests/test_dsi_duplicate_*.py -q` from `apps/api`

### Final duplicate pass (May 2026 — uncommitted on `main`)
- **Normalization:** SA suffixes `rf`/`soc`/`soc ltd`/state-owned phrases; `&` → `and`; t/a fixes for `(t/a)`, `trading-as`, trailing `t/a`/`a/t`. `cc`/`npc` already stripped; safe vs BCS acronym gate (`\bcc\b` word-boundary).
- **Filter:** `possible_duplicates_only` now excludes rows with `duplicate_review.decision` set (same SQL as `duplicate_unresolved_only`).
- **UI:** Both duplicate chips are **identical** after filter fix — **do not rename/remove** until user decides (was “Possible duplicates” vs “Duplicate review needed”).
- **Next:** User revalidates job **733** as definitive final duplicate pass; then weekly uploads.

## Runtime (local dev, no Docker)
- Web: http://localhost:3000 — `pnpm dev:web`
- API: http://localhost:8001 — `pnpm dev:api`
- Worker: `pnpm dev:worker` (Redis :6379)
- DB: `cip` on localhost:5432

## Scoped for later
- Server-side `duplicate_cluster_id` on validate; customer master merge (Phase E); VAT/phonetic; open peer cross-page

## Prior chat
Full arc: duplicate steward on job 733, commit `c774616`, revalidate started then environment crash — see agent transcript if needed.

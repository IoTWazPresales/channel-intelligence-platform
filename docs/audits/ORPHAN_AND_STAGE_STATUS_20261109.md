# Orphan re-check + stage status — 2026-11-09

**Tip:** `feat/integrate-20261103` @ `1aa9df5b` (plus stacked BACKLOG-200 commits on this PR base).
**Method:** re-read product code on the tip; do not trust the 2026-11-06 overnight orphan notes without a fresh hit.
**CURRENT.md:** deferred — that file is in open PR #60. Status that would go there is recorded in `docs/BACKLOG.md` (BACKLOG-221 + this audit) per Warren's standing rule.

## Stage status (planned Stage 1 vs tip)

| Item | Class | Evidence |
|------|-------|----------|
| Docs BACKLOG-210 / 215 / 216 Done | **DONE** | Merged via PR #57 |
| Pricing padding | **DONE** | Merged via PR #55 / related |
| Shipment test fix | **DONE** | Merged via PR #56 |
| D-0144 tenant mapping / `source_definition` | **DONE** | Migrations `20261103_0055` + `0060` + `tenant_mapping_scope.py` on tip |
| BACKLOG-200 dead `MasterColumnPickerDialog` | **SAFE-NOW → PR open** | PR #65 (this stack base); deletions + BACKLOG Done |
| N-0118 CST chain re-key / site grain | **WAITS-FOR-#60** | Open PR #60; touches CST apply + `docs/memory/CURRENT.md` |
| Competition suggested-match / price import | **SAFE-NOW (wire)** / recorded | Scorer still unused; UI copy still says no suggested matches / no price import — see BACKLOG-221 |
| Store/DC UI controls | **DONE (wiring)** | `ReplenishmentBoard.tsx` calls refresh, config, thresholds, lead-times, served-accounts; `StoreMap` pins — Nov 6 unmounted claim is stale |
| Listing capture health | **DONE (mount)** | `ListingCaptureHealth` imported and rendered from `MarketSurface` (skipped only on `/competition`) — Nov 6 no front-end hit claim is stale |
| URL pattern / autoconfig | **DONE (not orphan)** | Invoked from autoconfig path; false positive on Nov 6 list |
| N-0108 Cover/Brief LATERAL | **HELD / measure** | CURRENT tip already records lateral read timings; further NB re-time is ops, not a conflict-free code PR here |
| Role matrix / new KAM-PM-finance-approver roles (D-0029 Q3) | **HELD** | Warren accepted create-new-roles; route checks not built (BACKLOG-136) |
| Migrations / fresh-DB (BACKLOG-214 etc.) | **HELD** | Serial; not started from this job |
| Anything overlapping #60's 7 paths | **WAITS-FOR-#60** | `CONTEXT.md`, `cst_apply_sync.py`, `customer_sell_through.py`, `customer_sell_through_apply.py`, CST tests, `docs/memory/CURRENT.md` |

## Orphan re-check (true leftovers)

### Still orphan / half-built

1. **`score_competitor_candidate`** in `apps/api/app/services/competition/matching.py` — exported from `services/competition/__init__.py`; **no production caller** outside that package (2026-11-09 search). Stored scores can still be listed; suggested-match proposal is not wired.
2. **Competitor price import** — `MarketSurface.tsx` still states there is no import for competitor prices (empty substrate view).
3. **Suggested matches UI** — `MarketSurface.tsx` still states suggested matches are not offered on the competition mapping screen.

### Cleared (were orphans on 2026-11-06; not orphans on tip)

1. **Store/DC refresh / config / thresholds / lead-times / assignment** — wired in `ReplenishmentBoard.tsx` (+ tests).
2. **Capture health panel** — `ListingCaptureHealth` mounted from `MarketSurface` for non-`/competition` paths.
3. **URL pattern / autoconfig** — not an orphan.

### Dead-code deletion already opened

- **BACKLOG-200** `MasterColumnPickerDialog` — deleted in PR #65. Repo-wide leftover hits are historical (`.eif/audit/**`, docs).

## Overlap table (do not parallel)

| Work | Paths | Overlaps |
|------|-------|----------|
| PR #60 | 7 CST/CURRENT paths above | Blocks any CST apply or CURRENT edit |
| PR #65 / this stack | `MasterColumnPickerDialog*`, `docs/BACKLOG.md` | BACKLOG.md shared — stack serial docs PRs |
| Competitor wire (future) | `services/competition/**`, `MarketSurface.tsx`, competition endpoints | Serial with listing lens edits if same files |
| Store/DC further product work | `features/store-dc/**`, `store_dc.py` | Free of #60; D-0142/D-0143 product rules already accepted |

## Class legend

- **DONE** — merged or proven on tip; do not rebuild.
- **SAFE-NOW** — zero overlap with #60; may open a PR (docs or code) without waiting.
- **WAITS-FOR-#60** — shares files with #60 or needs CURRENT.md.
- **HELD** — needs Warren decision, migration serial, or ops apply.


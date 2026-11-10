# Orphan re-check + stage status — 2026-11-10

**Tip:** `feat/integrate-20261103` @ `d0972d50` (Merge #75 BACKLOG-006 line_ids).
**Method:** re-read product code and BACKLOG statuses on the tip; do not trust the 2026-11-09 orphan register without a fresh hit. Prior pass kept at `docs/audits/ORPHAN_AND_STAGE_STATUS_20261109.md`.
**CURRENT.md:** updated in the same docs PR (was parked while #60 owned that path; #60 is merged).

## Stage / merge status vs tip

| Item | Class | Evidence |
|------|-------|----------|
| Docs BACKLOG-210 / 215 / 216 Done | **DONE** | Stage-1 group (#55/#56/#57) |
| Pricing padding / shipment test / D-0144 tenant mapping | **DONE** | Stage-1 group + mig `0055`/`0060` |
| BACKLOG-200 dead `MasterColumnPickerDialog` | **DONE** | #65; file absent on tip |
| N-0118 CST chain re-key / site grain | **DONE** | #60 (`46c98213`); CURRENT tip notes retained |
| N-0118 NB1/NB3 | **DONE** | #68; NB2 index still **HELD** (migration) |
| BACKLOG-221 competition propose + price import | **DONE** | #67 + residual copy #70; `propose.py` calls `score_competitor_candidate`; `POST /competition/mappings/propose` + `POST /competition/prices/import` |
| BACKLOG-006 slim mapping-candidates `line_ids` | **DONE** | #70 tab-counts + #75 omit `context.line_ids` from list/paginated payloads |
| D-0025 BOM Not Ready default unticked | **DONE** | #71; `_PREFERRED_SHEET_KEYS` = shipped/unship; `_DEFAULT_EXCLUDED_SHEET_KEYS` includes bom not ready. BACKLOG-046 remaining scope still **Partial** |
| BACKLOG-222 Brief `promo_not_activated` | **DONE** | #72 |
| D-0119 / BACKLOG-223 stock carry-forward | **DONE** | #73 (`44cafc15`); flag `distributor_stock.on_hand_carried_forward` |
| D-0038 SOH tolerance flag | **DONE** | #74; tenant profile `soh_tolerance_pct` (default 0.10); recorded on BACKLOG-135 Partial |
| Decisions record (16 items) | **DONE** | #69 (`docs/decisions/DECISIONS_20261109_WARREN.md`) |
| Store/DC UI controls | **DONE (wiring)** | unchanged since 2026-11-09 |
| Listing capture health | **DONE (mount)** | `ListingCaptureHealth` still mounted from `MarketSurface` |
| Stage 1b grants on cip | **DONE** | `20261105_0058`–`0060` applied 2026-11-05 14:51 SAST; docs were stale at 0057 |
| D-0035 smoke-case removal | **leave in** | Warren 2026-11-10: leave smoke case in cip |
| Committed `.cip-alembic-smoke-pg` data dir | **DONE (this PR)** | Untracked + gitignored; no history rewrite |
| Open PRs into `feat/integrate-20261103` | **none** | GitHub list 2026-11-10 |

## Orphan re-check (true leftovers)

### Cleared since 2026-11-09

1. **`score_competitor_candidate` / suggested matches / competitor price import** — production caller `propose_competitor_mappings` + MarketSurface Propose/import UI (#67/#70).
2. **BACKLOG-006 `context.line_ids` on list payloads** — omitted on list + paginated responses (#75); DB context still stores ids for steward apply.
3. **Dead `MasterColumnPickerDialog`** — deleted (#65).

### Still open / held (not orphans of unmounted code)

1. **BACKLOG-046 residual** — union headers only from in-scope sheets; skipped-sheet badge; detect_report_type allowlist guard; optional BOM feed.
2. **BACKLOG-051 post-apply import reconciliation report** — still **Parked**; no `GET /import-jobs/{id}/reconciliation` (unrelated SOH/PO reconciliation tables/endpoints exist). Greenfield API+UI+export; TRIGGER not fired.
3. **BACKLOG-223 leftovers** — web chrome for carried-forward flag; non-standard calendars refused; past-count read speed-up.
4. **D-0038 leftovers** — decimal boundary tests / VAT basis still called out on BACKLOG-135.
5. **HELD** — migrations / `cip` writes: N-0118 apply to cip, listing seed, N-0100 part B, BACKLOG-214, NB2 index, D-0034 cleanup. Stage 1b grants **DONE** (`20261105_0058`–`0060` applied 2026-11-05 14:51 SAST). D-0035: leave smoke case in (Warren 2026-11-10).
6. **BACKLOG-136** — new KAM/PM/finance/approver roles accepted; route checks not built.
7. **docs/memory/ROADMAP.md** — still lists BACKLOG-006 as Parked (legacy phased file; prefer BACKLOG.md / docs/ROADMAP.md). Not rewritten in this pass (status truth lives in BACKLOG.md).

## Class legend

- **DONE** — merged or proven on tip; do not rebuild.
- **Partial** — core path shipped; residual rows still open in BACKLOG.
- **Parked** — TRIGGER not met.
- **HELD** — needs Warren decision, migration serial, or ops apply.

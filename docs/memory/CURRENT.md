# CURRENT state

**Last updated:** 2026-09-18 (build session: picker unify, mappings copy, Start work cards; item 4 stopped)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** Start work ActionCard restyle `d25a927`. ColumnPickerDialog `7656f67`. Mappings queue copy `39f457d`. Prior: Import Center/Market fold `b5f7e13`; collision counts `57348e8`; Lineup ApprovalBadge `b6e38fe`; Payments leftover `0b45f9a`; Cover `?product=` `3abad04`; grid parity `9e739da`; light theme `2e0c2a2`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **2026-09-18 build session (never main, no GOV-008):** BACKLOG-192 `ColumnPickerDialog` size md/wide `7656f67` (docs `1da81cd`). BACKLOG-197 mappings queue copy `39f457d` (docs `93ece93`). Start work ActionCards paper/icons/approved copy `d25a927`. Item 4 per-line column sets **stopped**: `catalog_product` is live (18157 rows, all linked to `dim_product`) — BACKLOG-198.
- **GOV-008 N-0027:** Independent review `GOV008_N0027_20260916` / `gov-022`. Verdict **VERIFIED_WITH_LIMITATIONS**. Node **complete**. Mapping-page restore-vs-retire copy is Done (`39f457d`). `StewardQueueOverview` still has leftover D-0002 wording (FOUND, not in this session’s mappings-page edit).
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0011 KEEP: `entity_mapping_queue` is pipeline state, not a UI to restore or retire.
- **NS21:** D-0011 KEEP (path C) accepted; supersedes D-0006 and D-0002. N-0027 AC1 rewritten (D-0011). Handover: `docs/design/gov-008-n0027-n0029-handover.md`.
- **NS20:** N-0028 `verification.rendered` / `verification.referent` reset pending. N-0029 `quality.design_signatures` reset pending.
- **NS18 / N-0028:** Overview Start work is `StartWorkLaunch` + `ActionCard` (`21d9182` structure, `d25a927` paper/icons/copy). Steward-queue href stays `/admin/mappings`.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Does not mint `cpor_case`.
- **Programme:** PRG-20260831T145514. **N-0018–N-0027 complete.** **N-0028, N-0029** `in_progress` / `validate`. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. N-0028 390 composition is implemented; 2026-09-18 Start work cards verified on live `/brief` as admin (click Import a lineup → `/admin/imports?unified=1`). 390×844 viewport was not set (no `browser_cdp`).

**Next:** Warren decides BACKLOG-198 (`catalog_product` vs per-line `column_mapping_memory`). Independent GOV-008 of **N-0028 only** remains out of this session. Ignore `GOV008_N0025_N0029_20260915`.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 Done. BACKLOG-193 AG Grid Enterprise. BACKLOG-197 Done. BACKLOG-198 per-line column sets vs live catalogue. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

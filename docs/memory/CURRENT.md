# CURRENT state

**Last updated:** 2026-09-18 (investigate/scope/design: catalogue, remaining work, API specs, settlement lab)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** StewardQueueOverview D-0011 copy `3f101a9`. Settlement lab A/B `daf0503`. Specs/docs `49e0836`. Ledger `19f26f8`. Prior: Start work ActionCard `d25a927`. ColumnPickerDialog `7656f67`. Mappings queue copy `39f457d`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **2026-09-18 investigate/scope/design (never main, no GOV-008, no node complete):** BACKLOG-198 catalogue is live; EAV write is gated off (`pm_write_legacy_eav` default False → `write_attribute_values=False` in `pm_commit_catalog.commit_catalog_and_eav`). `cpor_case` has `ended`/`settled`, **no paid/closed column** — report migration, do not run. Settlement lab compositions at `/design-lab/funding?lens=settle` (`alt=a|b`); production `/commercial-planner/cpor-cases/[id]` untouched. Specs: `docs/EXTERNAL_API_OUTBOUND.md`, `docs/EXTERNAL_API_INBOUND.md`. StewardQueueOverview leftover D-0002 copy aligned to D-0011 (`3f101a9`). Playwright MCP / `cursor-ide-browser` **not in this session’s tool catalog** — 1280×800 and 390×844 renders UNABLE_TO_RENDER; HTTP 200 on both lab URLs is not smoke.
- **2026-09-18 prior build session:** BACKLOG-192 `ColumnPickerDialog` size md/wide `7656f67`. BACKLOG-197 mappings queue copy `39f457d`. Start work ActionCards paper/icons/approved copy `d25a927`. Item 4 per-line column sets **stopped** → BACKLOG-198.
- **GOV-008 N-0027:** Independent review `GOV008_N0027_20260916` / `gov-022`. Verdict **VERIFIED_WITH_LIMITATIONS**. Node **complete**. Mapping-page restore-vs-retire copy Done (`39f457d`). StewardQueueOverview second instance now Done (`3f101a9`).
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0011 KEEP: `entity_mapping_queue` is pipeline state, not a UI to restore or retire.
- **NS21:** D-0011 KEEP (path C) accepted; supersedes D-0006 and D-0002. N-0027 AC1 rewritten (D-0011). Handover: `docs/design/gov-008-n0027-n0029-handover.md`.
- **NS20:** N-0028 `verification.rendered` / `verification.referent` reset pending. N-0029 `quality.design_signatures` reset pending.
- **Programme:** PRG-20260831T145514. **N-0018–N-0027 complete.** **N-0028, N-0029** `in_progress` / `validate` (PROGRAM.yaml). Generated `.eif/CURRENT.md` showing empty frontier is **stale vs PROGRAM.yaml** — tree nodes win. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. This session did not set 390×844 (`cursor-ide-browser` namespace absent; `browser_resize` not callable). Do not use `browser_cdp`.

**Next:** Warren chooses settlement composition A vs B (lab only). Warren answers BACKLOG-198 (nest per-line maps in `column_mapping_memory`, do not revive EAV). Independent GOV-008 of N-0028/N-0029 remains out of this session — do not run chrome review before the settlement desk and proposed-vs-executed surface. Ignore `GOV008_N0025_N0029_20260915`.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement **production** route (lab A/B exist). BACKLOG-193 AG Grid Enterprise. BACKLOG-197 Done (mappings + StewardQueueOverview). BACKLOG-198 per-line column sets vs live catalogue. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED. Paid/closed on `cpor_case` is a future migration.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

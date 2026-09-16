# CURRENT state

**Last updated:** 2026-09-16 (NS20 ledger-align: N-0028 verification reset, D-066)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `21d9182` (Start work ActionCard launch strip). Prior pins: BACKLOG-196 `aee82a7`; steward UX `4d9079b`. NS19 ledger `d872fb5` / views `e15be60` / payloads `6d00da8`. NS20 ledger `87e9788` / views `43ec48a` / payloads `1127b93` / docs `ea34cc8`; programme snapshot **851** (run `NS20_LEDGER_ALIGN_20260916` / actor `gov-020`).

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **NS20 (this session, ledger/docs only):** N-0028 `verification.rendered` and `verification.referent` reset to **pending** via `node.verification` (cleared GOV008_N0025_N0029_20260915 pass provenance). quality.design_signatures / design_divergence already pending from NS19 (`live_panel_wrapper` retained only as stale_signatures). N-0029 `quality.design_signatures` reset to **pending** (`payment_evidence_code_unread` superseded by `aee82a7`). Nodes stay `in_progress` / `validate`. Leases released. Do not complete. Do not run GOV-008.
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0002 remains proposed; D-0006 remains accepted (deferral). Do not supersede D-0006.
- **NS18 / N-0028 (committed `21d9182`):** Overview Start work is `StartWorkLaunch` + `ActionCard`. Steward-queue href stays `/admin/mappings`.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Does not mint `cpor_case`.
- **Programme:** PRG-20260831T145514. **N-0018–N-0026 complete.** **N-0027, N-0028, N-0029** `in_progress` / `validate`; leases released. Do not complete. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. N-0028 390 composition is implemented; independent GOV-008 not recorded after AC/tree change.

**Next:** Independent GOV-008 of N-0027–N-0029 after Warren decides D-0002 re-frame (do not supersede D-0006 in a GOV-008 session). Do not complete those nodes in an implementation chat.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

# CURRENT state

**Last updated:** 2026-09-16 (NS21 path C KEEP: D-0011, N-0027 AC1, N-0028 optional quality)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `21d9182` (Start work ActionCard launch strip). Prior pins: BACKLOG-196 `aee82a7`; steward UX `4d9079b`. NS20 ledger `87e9788` / views `43ec48a` / payloads `1127b93` / docs `ea34cc8`. NS21 ledger `8433ef4` / views `c42cd17` / payloads `7417f68`; programme snapshot **864** (run `NS21_PATH_C_KEEP_20260916` / actor `gov-021`).

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **NS21 (this session, ledger/docs only):** D-0011 KEEP (path C) accepted; supersedes D-0006 and D-0002. N-0027 AC1 rewritten only (rev **48**). N-0028 `quality.rendered_comparison` / `quality.design_sameness_review` / `quality.design_state_coverage` reset to **pending** via `node.quality` (engine accepted optional dims). Nodes stay `in_progress` / `validate`. Leases released. Do not complete. Do not run GOV-008. Handover: `docs/design/gov-008-n0027-n0029-handover.md`.
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0011 KEEP: `entity_mapping_queue` is pipeline state, not a UI to restore or retire.
- **NS20:** N-0028 `verification.rendered` / `verification.referent` reset pending. N-0029 `quality.design_signatures` reset pending.
- **NS18 / N-0028 (committed `21d9182`):** Overview Start work is `StartWorkLaunch` + `ActionCard`. Steward-queue href stays `/admin/mappings`.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Does not mint `cpor_case`.
- **Programme:** PRG-20260831T145514. **N-0018–N-0026 complete.** **N-0027, N-0028, N-0029** `in_progress` / `validate`; leases released. Do not complete. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. N-0028 390 composition is implemented; independent GOV-008 not recorded after AC/tree change.

**Next:** Independent GOV-008 of N-0027–N-0029, **one node per review**, per `docs/design/gov-008-n0027-n0029-handover.md`. Ignore `GOV008_N0025_N0029_20260915`. Do not complete those nodes in an implementation chat.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

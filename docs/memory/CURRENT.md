# CURRENT state

**Last updated:** 2026-09-17 (overnight mechanical close-out; no GOV-008)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** Import Center/Market fold `b5f7e13`. Collision counts `57348e8`. Prior: Lineup ApprovalBadge `b6e38fe`; Payments leftover `0b45f9a`; Cover `?product=` `3abad04`; grid parity `9e739da`; light theme `2e0c2a2`; Start work ActionCard `21d9182`; BACKLOG-196 `aee82a7`; steward UX `4d9079b`. NS21 KEEP D-0011 `929ad04`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Overnight 2026-09-17 (this session):** Items 2–7 shipped on this branch (never main). Item 1 N-0027 ledger already on origin (`c902fd9`). Item 8 read-only collision count on `cip` — see `docs/verify/backfill-source-key-collision-20260917.md`. BACKLOG-182/189/194/195 Done. BACKLOG-192 still parked (two pickers). BACKLOG-193 still parked (no AG Grid Enterprise). BACKLOG-197 parked (steward restore-vs-retire copy vs D-0011; do not fix in overnight).
- **GOV-008 N-0027:** Independent review `GOV008_N0027_20260916` / `gov-022`. Verdict **VERIFIED_WITH_LIMITATIONS**. Node **complete**. Limitation: leftover EntityMappingQueue chrome still says D-0002 restore-vs-retire → **BACKLOG-197**.
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0011 KEEP: `entity_mapping_queue` is pipeline state, not a UI to restore or retire.
- **NS21:** D-0011 KEEP (path C) accepted; supersedes D-0006 and D-0002. N-0027 AC1 rewritten (D-0011). Handover: `docs/design/gov-008-n0027-n0029-handover.md`.
- **NS20:** N-0028 `verification.rendered` / `verification.referent` reset pending. N-0029 `quality.design_signatures` reset pending.
- **NS18 / N-0028 (committed `21d9182`):** Overview Start work is `StartWorkLaunch` + `ActionCard`. Steward-queue href stays `/admin/mappings`.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Does not mint `cpor_case`.
- **Programme:** PRG-20260831T145514. **N-0018–N-0027 complete.** **N-0028, N-0029** `in_progress` / `validate`. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. N-0028 390 composition is implemented; independent GOV-008 not recorded after AC/tree change.

**Next:** Independent GOV-008 of **N-0028 only** (then N-0029), one node per session, per `docs/design/gov-008-n0027-n0029-handover.md`. Ignore `GOV008_N0025_N0029_20260915`. Click Start work ActionCards; prove URL change. Do not remediate leftover D-0002 chrome in a review chat (BACKLOG-197).

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-197 steward restore-vs-retire copy. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

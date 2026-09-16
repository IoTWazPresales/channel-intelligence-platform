# CURRENT state

**Last updated:** 2026-09-16 (GOV-008 N-0027 VERIFIED_WITH_LIMITATIONS; node complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `21d9182` (Start work ActionCard launch strip). Prior pins: BACKLOG-196 `aee82a7`; steward UX `4d9079b`. NS21 KEEP D-0011 `929ad04`. Programme snapshot **888** (run `GOV008_N0027_20260916` / actor `gov-022`).

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **GOV-008 N-0027 (this session):** Independent review `GOV008_N0027_20260916` / `gov-022`. Stale `GOV008_N0025_N0029_20260915` dims reset pending then re-passed. Playwright MCP 1280×800. `current_database()=cip` read-only. Verdict **VERIFIED_WITH_LIMITATIONS**. Node **complete**, lease released. Limitation: leftover EntityMappingQueue chrome still says D-0002 restore-vs-retire; D-0011 KEEP not reflected in that copy. Evidence: `.eif/audit/GOV008_N0027_20260916/independent-rendered-review.md`.
- **D-066 locked:** steward and mapping resolve inside `/admin/mappings?workspace=resolve`. Do not page-hop. D-0011 KEEP: `entity_mapping_queue` is pipeline state, not a UI to restore or retire.
- **NS21:** D-0011 KEEP (path C) accepted; supersedes D-0006 and D-0002. N-0027 AC1 rewritten (D-0011). Handover: `docs/design/gov-008-n0027-n0029-handover.md`.
- **NS20:** N-0028 `verification.rendered` / `verification.referent` reset pending. N-0029 `quality.design_signatures` reset pending.
- **NS18 / N-0028 (committed `21d9182`):** Overview Start work is `StartWorkLaunch` + `ActionCard`. Steward-queue href stays `/admin/mappings`.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Does not mint `cpor_case`.
- **Programme:** PRG-20260831T145514. **N-0018–N-0027 complete.** **N-0028, N-0029** `in_progress` / `validate`. Do not reopen N-0013.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844. N-0028 390 composition is implemented; independent GOV-008 not recorded after AC/tree change.

**Next:** Independent GOV-008 of **N-0028 only** (then N-0029), one node per session, per `docs/design/gov-008-n0027-n0029-handover.md`. Ignore `GOV008_N0025_N0029_20260915`. Click Start work ActionCards; prove URL change. Do not remediate N-0027 leftover D-0002 chrome in a review chat.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

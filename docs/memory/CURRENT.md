# CURRENT state

**Last updated:** 2026-09-15 (steward UX shipped; BACKLOG-196)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `4d9079b` (steward resolve workspace + Panel Start work). Last ledger pin: `2dbce4a` (GOV-008 N-0025/N-0026 complete). Last evidence pin: `52c006e`. Last views pin: `ad24c3e`. Last docs pin: `57969c1`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Charter (operator, this session):** Keep steward row → `/admin/mappings?workspace=resolve`. Keep Start work `Panel`/`PanelRow`. Amend N-0027/N-0028 ACs in the next programme session — do not restore Import Center `?job=` or outlined cards.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias. `EnterpriseDataGrid` clips cell overflow. Start work uses Overview `Panel`/`PanelRow`.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Overlay `GET …/overlay?code=` returns `focus_rows` via ORM equality on `external_case_code`. Does not mint `cpor_case`. No fuzzy match. Unit-tested. Live: unmatched `C19A50693` → import page shows 1 applied unlinked evidence row.
- **Programme:** PRG-20260831T145514. **N-0018–N-0026 complete.** **N-0027–N-0029** `in_progress` / `validate`; leases released. Do not reopen N-0013. D-0002 remains open.
- **GOV-008 N-0025–N-0029** (vs impl NS13–NS17 / `gov-001`): N-0025 **VERIFIED_WITH_LIMITATIONS complete**. N-0026 **VERIFIED complete**. N-0027–N-0029 **VERIFIED_WITH_LIMITATIONS** not complete pending AC amend (workspace vs `?job=`; Panel vs cards) plus live BACKLOG-196 smoke. Evidence `.eif/audit/GOV008_N0025_N0029_20260915/independent-rendered-review.md`.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844 (above Attention).

**Next:** Programme session: amend N-0027 AC (resolve workspace) and N-0028 AC (Panel Start work). Independent GOV-008 re-review of those nodes after AC amend — not in the implementation chat. Do not run GOV-008 in an implementation session.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).

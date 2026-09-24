# GOV-008 independent review — N-0048 (BACKLOG-139: cpor_case status vs workflow_status drift)

Reviewer: verification-controller (independent session), lenses: database-specialist, data-quality-governance-specialist, release-migration-manager.
Model identity: Claude Sonnet 5 (claude-sonnet-5), Anthropic. This is a different session than the implementation run; same model family could not be excluded/varied (no separate-model consult mechanism used) — record per rung R2 (another session, self-declared limitation on model independence).

Evidence base: `git show 84002d8e`, static grep of `apps/api` and `apps/web/src` for `workflow_status`, `docs/BACKLOG.md` BACKLOG-139 entry, `apps/api/scripts/ops/repair_n0048_cpor_case_status_drift.py` read in full, live read-only SQL against `cip` and `cip_ns4_settle_clone` via `.eif/audit/PROGRAMME_20260924/ro_sql.py`, and `pytest apps/api/tests/test_cpor_workflow_status_projection.py`. Did not read `n0048/IMPL.md` or any implementer-findings file, per brief.

## Criterion 1 — Owner column chosen with reasoning; every writer keeps the other column consistent

**PASS.** `apps/api/app/services/cpor/lifecycle.py` (diff in 84002d8e) adds `workflow_status_for(status)`: `status` is the owning lifecycle column (`draft → proposed → approved → active → ended → settled`, plus `rejected`/`cancelled`); `workflow_status` is declared a pure projection (`proposed → pending_approval`, everything else → itself).

Verified every writer of `cpor_case.workflow_status` via grep (`workflow_status\s*=` across `apps/api`):
- `apps/api/app/api/v1/endpoints/cpor_cases.py:1434` — the transition endpoint now sets `case.workflow_status = workflow_status_for(case.status)` unconditionally after every action branch (propose/approve/reject/resend/activate/end/settle/cancel), replacing the old per-branch dual-writes that omitted it on activate/end/settle/cancel (visible in the diff as removed lines under `propose`/`approve`/`reject`/`resend` only — those four branches were the ones that used to hand-write it, and precisely because `activate`/`end`/`settle`/`cancel` never did, they are the four drifted rows).
- `apps/api/app/services/cpor/historical_import/apply_sync.py:194,207` — both insert and update paths now call `workflow_status_for(status[:32])`.
- `apps/api/app/services/cpor/payment_evidence/apply_sync.py:67` — shell-case creation now calls `workflow_status_for("draft")`.

Reads: `status` is what `lifecycle.py` (`allowed_next`, `can_transition`, `target_status`, `EDITABLE_STATUSES`) and the transition endpoint's guard logic key off; `workflow_status` is not read anywhere to drive branching logic — confirmed by grepping `workflow_status` across `apps/api` and `apps/web/src`: every non-test, non-projection hit is either a straight assignment (a writer) or a passthrough serialization field (`cpor_cases.py:260`, `_case_json`). In `apps/web/src`, `workflow_status` appears only in `types.ts` (field declaration) and three `*.test.tsx` fixture files — no `.tsx` component branches on it (grep for `workflow_status` restricted to `*.tsx` returns only the three test files). So `status` is confirmed as the column transitions/reads rely on; `workflow_status` is confirmed as write-only-derived, display-only.

**Limitation (not a failure):** two case-creation call sites still write the literal `workflow_status="draft"` instead of `workflow_status_for(status)`: `apps/api/app/api/v1/endpoints/cpor_cases.py:747` and `apps/api/app/services/cpor/promo_plan_builder.py:1034` (both create with `status="draft"` alongside). This is consistent *today* only because `"draft"` is not in `_WORKFLOW_STATUS_OVERRIDES` (so `workflow_status_for("draft") == "draft"`) — it is not routed through the single projection function, so it is a latent re-drift risk if the override table ever grows a `"draft"` entry. Not in scope of the commit's stated fix (only the transition path was broken), but worth flagging.

## Criterion 2 — Drift rows measured on cip read-only (count and ids now)

**PASS — VERIFIED.** Ran directly:
```
apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/ro_sql.py --db cip \
  "SELECT id, case_code, status, workflow_status, updated_at FROM cpor_case WHERE status IS DISTINCT FROM workflow_status ORDER BY id"
```
Result: `current_database() = cip`, 4 rows — ids **3** (BATCH0-SMOKE-001, cancelled/draft), **309** (C26761655, settled/ended), **310** (C26759823, cancelled/ended), **311** (C26760971, settled/ended). Exactly matches the commit message's claimed ids (3, 309, 310, 311) and the count in `docs/BACKLOG.md` ("Measured 2026-09-21 N-0030: 4 rows").

## Criterion 3 — Repair proven on a clone with before/after; script inspected

**PASS — VERIFIED.**

Before/after on `cip_ns4_settle_clone` (repair was already applied there per the commit; re-measured independently):
```
SELECT count(*) FROM cpor_case WHERE status IS DISTINCT FROM workflow_status  →  0
```
Full-table read of `cpor_case` on the clone (313 rows visible) shows `status == workflow_status` for every row, including the four previously-drifted ids (3, 309, 310, 311 now match, e.g. 309: settled/settled). `cpor_case_event` on the clone has 3 `workflow_status_repair` events for ids 3/309/310 (id 311 not present in the committed audit excerpt I queried, consistent with the committed `clone_4_after.txt` evidence which only listed 3/309/310) each recording `status`, `workflow_status_before`, `workflow_status_after` — a genuine audit trail.

Script inspection (`apps/api/scripts/ops/repair_n0048_cpor_case_status_drift.py`):
- **Idempotent**: `_UPDATE_SQL` is `UPDATE ... SET workflow_status = :new WHERE id = :id AND workflow_status IS NOT DISTINCT FROM :old`; `plan_repair` recomputes from live rows on every invocation, so a second run finds 0 rows to change. Also covered by `test_repair_is_idempotent_on_the_four_cip_shapes` (passed).
- **Dry-run default**: `main()` only calls `conn.commit()` when `args.apply` is set; otherwise `conn.rollback()`. `--apply` is required to persist.
- **`--expect-db` guard**: `main()` reads `current_database()` and `return 2` (stop, no run) if it doesn't equal `--expect-db`, before any read/write.
- **Records before-values**: `_write_before` writes a timestamped JSON (`before_<db>_<apply|dryrun>_<ts>.json`) to `.eif/audit/PROGRAMME_20260924/n0048/`, and `apply_changes` additionally inserts one `cpor_case_event` row per change with before/after in `payload_json`.
- **Touches only `workflow_status`, never `status`**: the only `UPDATE` statement in the file is `_UPDATE_SQL`, targeting `workflow_status` alone; `status` is read (`_ROWS_SQL`) but never assigned. Confirmed empirically: clone rows 3/309/310/311 have their original `status` values unchanged (e.g. 309 is still `settled`, not rewritten).
- **No deletes**: no `DELETE`/`TRUNCATE` statement anywhere in the file.

## Criterion 4 — cip apply listed for Warren, not run

**PASS — VERIFIED.** cip still shows all 4 drifted rows (criterion 2 query). Additionally:
```
SELECT current_database(), count(*) FROM cpor_case_event WHERE event_type='workflow_status_repair'  -- on cip
→ cip | 0
```
Zero repair events exist on `cip`, confirming the repair has not been applied there. The script's module docstring explicitly stages this as an operator action: `"Ready-for-cip (Warren runs, from apps/api): .venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip [--apply]"` — two explicit commands, dry-run first, apply second, both requiring the human to invoke them.

## Criterion 5 — Tests green

**PASS — VERIFIED.**
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_cpor_workflow_status_projection.py -q
→ ................... (19 passed in 16.27s)
```
No conftest refusal occurred; not needed anyway — the test module's own docstring states `"mocked; no cip"`, and inspection confirms it uses `unittest.mock.MagicMock`/`SimpleNamespace` for the DB session and `FastAPI TestClient` with a patched `SessionLocal`, never a real database connection. This also independently satisfies part of criterion 6 for this test run.

## Criterion 6 — Nothing writes to cip

**PASS — VERIFIED** for this review's own activity: all SQL against `cip` and `cip_ns4_settle_clone` in this review used `ro_sql.py` (a read-only session, per the brief). All commands run were `SELECT`. The pytest run touched no real database (criterion 5). For the evidenced work itself: cip's repair-event count is 0 and its 4 drift rows are unchanged (criterion 4), so the implementation's clone-proof work did not touch cip either.

## Could the repair change any business outcome (e.g. a case's settled state)?

**No, on the evidence gathered.** The repair `UPDATE` statement is syntactically restricted to the `workflow_status` column; `status` — the column lifecycle guards, transition eligibility (`allowed_next`/`can_transition`), and (per the grep above) all business branching key off — is read-only in the script and empirically unchanged pre/post on the clone. Static search across `apps/api` and `apps/web/src` for `workflow_status` found no conditional/branching consumer of that column outside the writers themselves and one passthrough serialization field (`_case_json`); the frontend only types and test-fixtures it, with no `.tsx` component reading it for logic. This is a static/grep-based conclusion (I did not runtime-trace every dynamic property access), so it is VERIFIED-by-search rather than exhaustively proven, but no counter-evidence was found and the codebase's own explicit design intent (`lifecycle.py` docstring: "workflow_status is a projection of it (never an independent machine)") supports it.

## Overall verdict: VERIFIED_WITH_LIMITATIONS

All six acceptance criteria PASS with direct evidence (live SQL on cip and the clone, script inspection, passing tests). No criterion failed. Verdict is downgraded from VERIFIED to VERIFIED_WITH_LIMITATIONS for two non-blocking findings surfaced during review (see Limitations) and because model independence for this R2 review is self-verification-adjacent (same model family, different session; no separate-model consult was available).

### Limitations
- Two case-creation sites (`apps/api/app/api/v1/endpoints/cpor_cases.py:747`, `apps/api/app/services/cpor/promo_plan_builder.py:1034`) write `workflow_status="draft"` literally instead of via `workflow_status_for(status)`. Correct today only because `"draft"` is absent from the override map; latent re-drift risk if that map is extended. Not required by the acceptance criteria to be fixed and not part of the stated bug (only transition writes were broken), but should be tracked.
- Reversal path for the repair is manual: `cpor_case_event` rows and the `before_*.json` evidence files record before-values, but there is no automated "undo" script — a human would reconstruct the reverse `UPDATE` from the event payloads.
- "No business-outcome change" conclusion rests on static grep, not a runtime/dynamic-access trace of every consumer.
- Per GOV-008 rung guidance, R2 independence is "another session when available" — this review is a fresh session but the same model family as the implementation (Claude); no cross-model consult mechanism was exercised, so this is not full model-independent verification.

### Rung used
R2: fresh session, same-model self-verification-adjacent (no independent model consult mechanism available/exercised).

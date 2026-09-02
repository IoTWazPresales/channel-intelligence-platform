# NS-4 Settlement — Independent re-review (gov-008)

**Run:** NS4_INDEPENDENT_REREVIEW_20260902  
**Actor:** gov-008  
**Date:** 2026-09-02  
**Implementation run preserved:** NS4_SETTLEMENT_IMPL_20260902  
**Remediation run reviewed:** NS4_SETTLEMENT_REMEDIATION_20260902  
**Verdict:** **PASS** — remediation closes prior ux/content blocks; settle confirm clone proof accepted with test-hygiene note

## Programme state before review

| Field | Value |
|-------|-------|
| Programme | PRG-20260831T145514 rev **158** |
| PROGRAM_LOG SHA256 (before) | `863f95cf2aab1cf30cfd222ebb8f784ce617fd854c40976a31bab802e03c8b68` |
| PROGRAM_LOG events (before) | **158** |
| N-0008 | `in_progress` @ `verify`, node revision **39** |
| gates_valid | **false** (ux/content/design_execution_decisions pending) |
| independence_issues | **[]** |

## Prior failures (NS4_INDEPENDENT_REVIEW_20260902)

| Dimension | Failure |
|-----------|---------|
| **ux** | Apply button inert; From/To/BU/Customer pseudo-selects not labeled deferred |
| **content** | Apply CTA styled active without effect |
| **verification.rendered evidence** | `settle_e2e_clone: not_executed` — unmitigated settle confirm path risk |

Deferral of structural period/BU/customer filters was **never** the failure (`design_divergence` PASS retained).

## Scope bar — remediation verdict

**PASS.** `SettlementScopeBar.tsx` now renders deferred structural fields with dashed borders, muted typography, `aria-disabled="true"`, tooltip *"Period, BU, and customer filters are not active yet"*, and **Apply (not active)** as a `disabled` button (not primary CTA styling). State combobox and Saved view remain operable.

## UX / content

| Check | Result |
|-------|--------|
| Deferred controls visibly non-interactive | PASS (desktop + mobile 390×812) |
| Operable controls still work | PASS (State, Saved view, Reset, queue→case) |
| Apply honesty labeling | PASS — `Apply (not active)` + `aria-label` |
| No regression to accepted composition | PASS |

## Settle confirm clone evidence

Inspected `apps/api/tests/test_cpor_settle_confirm_clone.py` and executed test run output (this review).

| Check | Established from output |
|-------|-------------------------|
| Database identity | `resolved DATABASE_URL_SYNC=postgresql+psycopg://cip:cip@127.0.0.1:5432/cip_ns4_settle_clone`; `current_database()` asserted `cip_ns4_settle_clone` — **not cip** |
| Real service path | `TestClient(app)` → `GET …/settlement` preview → `POST …/transition` with `action: settle` (not direct status SQL) |
| Blocked FX | `409`, `detail.code == "fx_blocked"` |
| Allowed FX | `200`, `status == "settled"` |
| Settled count delta | `settled_before=210` → `211` after allowed settle → `210` after cleanup |
| Cleanup mechanism | **`_delete_case` hard-deletes** `CporCaseEvent` + `CporCase` rows — **does not conform** to product soft-supersede principle; acceptable as disposable-clone test hygiene **finding** (pattern risk for future destructive-path tests) |

Clone proof closes the prior unmitigated settle-path risk for product behaviour. Test cleanup pattern recorded separately — not a product defect.

## Rendered re-review (live stack)

Stack: web `:3000`, API `:8001` (no preflight refusal observed).

### Desktop 1280×900

| Zone | Verdict |
|------|---------|
| Book + regime strip | PASS — Book R 6,021,148.88; Outstanding matches |
| Scope bar | PASS — deferred controls honest; State + Saved view active |
| Book read | PASS — shape narrative + portfolio tiles |
| Queue | PASS — open cases, settle readiness column |
| Case pane `?case=311` | PASS — full workspace, Settlement tab |
| Settle preview | PASS — zero-claims context; FX blocked alert; **Confirm settlement disabled**; Cancel closes |

### Mobile 390×812

PASS — nav drawer; scope bar wraps; disabled Apply visible; queue/case stack.

### First paint (cold)

Navigated `/commercial-planner/cpor-cases` fresh. Book total, regime strip, and Book read figures resolved on first paint without manual reload. **PASS.**

## Tests (this re-review)

| Command | Result |
|---------|--------|
| `vitest run SettlementScopeBar.test.tsx settlementViews.test.ts` | 4 passed |
| `pytest test_settlement_book_read.py test_cpor_fx_enforcement.py test_cpor_settle_readiness.py` | 13 passed |
| `pytest test_cpor_settle_confirm_clone.py -s` | 1 passed (`cip_ns4_settle_clone`) |

## N-0009 Lineup finding (record only)

Confirmed from source: `LineupScopeBar.tsx` — Apply styled as primary CTA with **no handler**; From/To/BU/Customer static pseudo-selects without disabled labeling. Same inert-control defect as pre-remediation Settlement. N-0009 programme status **not** reopened. BACKLOG entries written.

## Gates re-reviewed this run

| Dimension | Action | Rationale |
|-----------|--------|-----------|
| ux | **PASS** (new) | Was blocked → pending after remediation |
| content | **PASS** (new) | Was blocked → pending after remediation |
| design_execution_decisions | **PASS** (new) | Invalidated to pending by remediation (consequential_action) |
| verification.rendered | **PASS** (evidence refresh) | Closes `settle_e2e_clone: not_executed` risk note |
| All other quality dims | **Preserved** | Prior NS4_INDEPENDENT_REVIEW_20260902 PASS unchanged |

## Quality dimension summary

| Dimension | Result |
|-----------|--------|
| design_artifact_class | pass (preserved) |
| design_divergence | pass (preserved) |
| design_signatures | pass (preserved) |
| rendered_comparison | pass (preserved) |
| design_sameness_review | pass (preserved) |
| design_interaction_spec | pass (preserved) |
| design_state_coverage | pass (preserved) |
| design_identity_tokens | pass (preserved) |
| design_execution_decisions | **pass** (re-reviewed) |
| ux | **pass** (re-reviewed) |
| a11y | pass (preserved) |
| rendered | pass (preserved) |
| content | **pass** (re-reviewed) |

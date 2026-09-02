# NS-4 Settlement — Independent rendered review (gov-008)

**Run:** NS4_INDEPENDENT_REVIEW_20260902  
**Actor:** gov-008  
**Date:** 2026-09-02  
**Implementation run preserved:** NS4_SETTLEMENT_IMPL_20260902  
**Verdict:** **FAIL** — scope bar control honesty (product remediation required)

## Provenance divergence

On N-0004, N-0007, and N-0009, ten quality dimensions were recorded under **implementation** provenance (`pass_actor: agent`) and three under **review** provenance (`pass_actor: gov-008`: `rendered_comparison`, `design_sameness_review`, `verification.rendered`).

N-0008's implementation session recorded **no** PASS events (all thirteen pending). This review assesses and records **all thirteen** dimensions under `NS4_INDEPENDENT_REVIEW_20260902` / `gov-008`. That is an intentional programme divergence: retroactive implementation self-certification was forbidden; fresh inspection is the only lawful source for the ten dimensions that prior nodes carried on the impl run.

## Governance pre-checks

| Gate | Result |
|------|--------|
| **2a** N-0006 dependency (`proposed`, no impl run) | Runtime `frontier()` blocks *starting* nodes with incomplete deps; **`node.status → complete` does not check `depends_on`**. Completion is lawful without N-0006 programme sync. Ledger inconsistency remains a programme hygiene issue, not a hard completion gate. |
| **2b** R3 `acceptance_policy.r3_plus: operator` | N-0008 carries `acceptance: auto` / `acceptance_state: not_required`. `gates_ok` only enforces operator acceptance when `acceptance == operator`. **Operator acceptance is not required** for this node unless Warren patches acceptance to operator. |

## Benchmark

- `docs/design/funding-settlement-r3.html` (high_fidelity)
- `docs/design/CIP_DESIGN_LANGUAGE.md` FROZEN v1.1, grammar 1, container Settlement

## Desktop 1280×900

| Zone | Product | Verdict |
|------|---------|---------|
| Task crumb Settlement / Book + regime strip | Live Book R 6,021,148.88; Outstanding matches | parity |
| Sticky scope bar | Structural From/To/BU/Customer static; State + Saved view work; **Apply inert** | **FAIL honesty** |
| Book read | Shape narrative + portfolio tiles + top outstanding `?case=` links | parity |
| Queue | 55 open rows; settle readiness column; AG Grid density | parity |
| Case pane `?case=311` | Full `CporCaseWorkspace`, default Settlement tab | parity |
| Settle preview | Zero-claims warning; FX blocked alert; confirm disabled when `fx_settle_allowed === false` | parity (safe inspect only) |

## Mobile 390×812

- Mobile nav drawer; scope bar wraps; queue and case stack vertically.
- Settlement tab, readiness chips, Settle case CTA visible in case pane.

## First paint (cold client)

Navigated `http://localhost:3000/commercial-planner/cpor-cases` without prior session on route. Book total, regime strip, and Book read figures rendered correct amounts on first paint (no manual reload). **PASS** — distinguishes normal async from the prior `formatGridMoney` crash (fixed).

## Scope bar — deferral vs honesty

**(a) Deferral disposition:** Structural period/BU/customer filtering is **not** in N-0008 acceptance criteria (high_fidelity + governing design input only). Deferral of those dimensions is defensible as `retain_with_deferrals` (precedent: N-0009 scope filter persistence).

**(b) Control honesty:** **FAIL.** From/To/BU/Customer render as bordered pseudo-selects without disabled styling or “not active” labeling. **Apply** is styled as the primary CTA but has **no handler** in `SettlementScopeBar.tsx` — it does not apply structural filters. State combobox and Saved view **do** filter via URL. Operable-looking inert controls violate the same FX-display honesty bar established on NS-1b.

## Case pane

Embedded workspace preserves full case workflow: FX mode toggles, readiness, claim upload/rollup, settlement grid, settle CTA. Deep link `?case=` selects case in pane. **PASS** preservation.

## Blocked FX / preview-confirm

Case C26760971 (`?case=311`): preview shows outstanding R 1,616,231.52, zero-claims warning, readiness chips, error “FX basis is not ready…”, **Confirm settlement disabled**. Cancel closes dialog. **PASS** — `fx_settle_allowed === false` blocks confirmation without executing settle.

## Settle path clone execution

No evidence of end-to-end settle **confirm** execution on a disposable DB clone in repo tests or audit history. API transition tests exist; UI confirm handler not exercised against live DB. **Unmitigated risk** — recorded under `verification.rendered` evidence; does not silently pass as full e2e proof.

## Preservation map

| Key | Running app |
|-----|-------------|
| `cpor_case_detail_route` | `CporCaseWorkspace` embedded in pane; `/commercial-planner/cpor-cases/[id]` route still in tree | PASS |
| `fx_settle_allowed` | Preview confirm disabled when FX blocked | PASS |
| `settle_readiness` | Chips + fx basis line in queue, case, confirm | PASS |
| `portfolio_intelligence_api` | `SettlementPortfolioRead` tiles on container | PASS |
| `deep_link_case_param` | `?case=311` loads case pane | PASS |
| `steward_imports` | Import historical + payment evidence links in queue toolbar | PASS |

## Tests (this review)

| Command | Result |
|---------|--------|
| `vitest run src/features/settlement/settlementViews.test.ts` | 3 passed |
| `vitest run page.fxReadiness.test.tsx` | 2 passed |
| `pytest tests/test_settlement_book_read.py test_cpor_fx_enforcement.py test_cpor_settle_readiness.py` | 13 passed |

## Sameness review

Challenged queue+case split vs benchmark single scroll — retained split for operator queue→case flow. Challenged AG Grid vs HTML table queue — retained grid for sort/pagination. **retain_frozen_benchmark** with scope-bar deferral.

## Remediation (implementation session — not this run)

1. **Scope bar honesty:** Disable or label inert Apply + structural fields; or wire structural filters. Minimum: `disabled` + tooltip “Period/BU/customer filters not active yet” per Lineup precedent.
2. Optional: programme sync N-0006 ledger (out of scope for this review).

## Quality dimension summary

| Dimension | Result |
|-----------|--------|
| design_artifact_class | pass |
| design_divergence | pass (`retain_with_deferrals`) |
| design_signatures | pass |
| rendered_comparison | pass (parity with deferrals) |
| design_sameness_review | pass |
| design_interaction_spec | pass |
| design_state_coverage | pass |
| design_identity_tokens | pass |
| design_execution_decisions | pass |
| **ux** | **blocked** (scope Apply + pseudo-filters) |
| a11y | pass |
| rendered | pass |
| **content** | **blocked** (inert Apply CTA) |

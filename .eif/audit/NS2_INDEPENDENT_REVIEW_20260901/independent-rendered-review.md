# Independent rendered review — N-0004

**Date:** 2026-09-01  
**Review run id:** `NS2_INDEPENDENT_REVIEW_20260901`  
**Review actor:** `gov-008`  
**Implementation run (preserved):** `NS2_RESUME_AFTER_RUNTIME_REPAIR_20260901`  
**Node:** N-0004 — NS-2 Brief and six-container nav collapse  
**Method:** Playwright + cursor-ide-browser against live stack (`:3000` / `:8001`); frozen benchmark served at `http://localhost:8765/brief.html`

## Programme context

- Historical status: `complete` (unchanged by this review)
- Prior gate invalidity: `design_sameness_review`, `rendered_comparison`, `verification.rendered` passed by implementation run (not independent)
- This review does **not** re-implement product code; it re-judges rendered evidence only.

## Benchmark inspected

| Artifact | Path / URL |
|---|---|
| Frozen high-fidelity benchmark | `docs/design/brief.html` |
| Design language | `docs/design/CIP_DESIGN_LANGUAGE.md` FROZEN v1.1 |
| Rendered benchmark (this run) | `http://localhost:8765/brief.html` @ 1280×900 |

## Live product inspected

| Surface | URL | Viewports |
|---|---|---|
| Brief landing | `http://localhost:3000/brief` | Desktop 1280×900; mobile 390×812 |
| Dashboard redirect | `http://localhost:3000/dashboard` | → `/brief` (middleware) |

Auth: `admin@local` dev session (standard local seed).

## `rendered_comparison` — PASS

Independent side-by-side judgment against frozen `brief.html`:

| Dimension | Benchmark | Live `/brief` | Verdict |
|---|---|---|---|
| Hierarchy | Spine → crumb → Read → blotter → footer | Same grammar-3 stack | Parity |
| Composition | 190px spine + main column grid blotter | `WorkbenchSpine` + signal grid | Parity |
| Density | 31–36px row rhythm, mono meta column | Matching row/meta/action columns | Parity |
| Scanability | Severity tick + bold lead + meta + action | Same four-column signal pattern | Parity |
| Visual grammar | Dark tokens, cyan Read tag, accent primary CTA | Tokens match FROZEN v1.1 (`#14161a`, `#3db8e8`, IBM Plex Mono) | Parity |
| Navigation | Six job containers + Reports/Admin | Brief, Lineup, Stock, Settlement, Response, Steward + util nav | Parity |
| Interaction clarity | One SUGGESTED hint on top steward action | Suggested chip on failed-imports row | Parity |
| Responsive | Static desktop artifact | Mobile: hamburger, drawer with full spine, scrollable blotter | Meets spec |
| Operator usefulness | Attention queue landing | Live API signals (4 rows) deep-link to steward/stock/settlement | Meets spec |

**Material deltas (acceptable, not regressions):**

- Live tenant stamp `DEFAULT · 26Q3` vs benchmark `ASUS SA · 26Q3` (environment label only).
- Live signal count/content reflects dev DB (4 signals) vs static demo (8 signals).
- Preservation semantics visible: inbound row documents pipeline fill % pending line-grain read model; sell-out gap excluded from ranked display per BLN-0001 preservation.
- Response spine badge absent (documented latent until NS-6).

**Conclusion:** Implementation achieves **high-fidelity parity** with the frozen benchmark; no material visual downgrade observed.

## `design_sameness_review` — PASS

Challenged whether retaining frozen benchmark execution was lazy duplication:

| Challenge | Finding |
|---|---|
| Stronger layout alternative? | Six-container spine + grammar-3 blotter is the accepted North Star architecture; reopening would violate node acceptance criteria. |
| Weak/generic patterns? | Signal rows are domain-specific (trust → position → money), not generic dashboard cards. |
| Chrome duplication (tasks in crumb)? | Brief chrome keeps attention queue clean; merging background-task affordances into crumb row would add noise without improving scan path. |
| Density vs benchmark? | Live Read strip is slightly shorter than static demo; acceptable trade for live API synthesis. |
| Missed material improvement? | None identified that would justify superseding FROZEN v1.1 without NS charter change. |

**Conclusion:** Retaining frozen benchmark design is **defensible**; sameness reflects correct adoption of the minimum accepted quality bar, not unthinking copy.

## `verification.rendered` — PASS

| Check | Result |
|---|---|
| Desktop `/brief` loads populated | 4 ranked signals, Read strip, footer timestamp |
| Mobile ~390px | Hamburger + drawer nav; Brief title bar; scrollable signals; labeled controls |
| `/dashboard` redirect | → `/brief` |
| Spine badges (live) | Brief 4, Stock 119, Settlement 78, Steward 30 |
| Signal actions | Links to `/admin/imports?status=failed`, `/sell-out`, `/shipping`, `/commercial-planner/cpor-cases` |
| Suggested primary CTA | On steward failed-imports row |
| Preservation signals | Pipeline fill % limitation and cost-basis gap surfaced in copy |
| Obvious layout breakage | None at desktop or mobile |
| A11y (rendered) | `aria-label` on mobile menu and sign-out; link-based actions |

**Conclusion:** Rendered product behaves as specified for NS-2 Brief operator landing.

## Independent verdict

All three independence-required gates **PASS** on rendered evidence. No product remediation required before programme validity restoration.

# N-0013 r3/r3.1 — Independent rendered review (GOV-008 continuation)

**Run folder:** `NS6_GOV008_R3_20260903`  
**Referent:** D-0008 (accepted) + N-0013 acceptance criteria  
**Prototype:** `http://localhost:3000/design-lab` (fixtures; no production API writes)  
**This document written:** 2026-09-03 (continuation session)

## Provenance — recovered vs newly completed

This is **not** a rerun of Fable and **not** a new CONSULT.

| Layer | Who | When | What |
|---|---|---|---|
| Author (not this review) | Fable 5.1, authoring run | 2026-09-02 | Design-lab + author `rendered-verification.md` (independence NONE) |
| CONSULT (IA questions only) | Claimed claude opus CLI, separate process | 2026-09-02 | `CONSULT_SEED.md` / `CONSULT_RESPONSE.md`. **CLI `--model` string not logged** — UNVERIFIED |
| GOV-008 start (paid, interrupted) | Subagent `b7a20859-2703-46c1-b066-30883696b525` (Other Models / Fable family) | 2026-09-03 14:23 +02 until usage-limit | Source/claim read; live Playwright; six desktop captures + `snap-d-overview.md`. **Did not write this file.** |
| GOV-008 remainder (this document) | Cursor Grok 4.6, later session | 2026-09-03 | Inspected recovered captures including `d-pf-casebook.png`; captured remaining required surfaces; wrote this file |

**Independence statement (truthful, not the original prompt’s canned line):**  
Reviewer of the recovered portion = separate agent context (subagent `b7a20859`), Fable family, own Playwright session 2026-09-03. Completing reviewer = different session and **different model family** (Grok 4.6). Recovered renders were **not** recaptured. New renders were taken against the same live `localhost:3000` design-lab.

This **does not** satisfy a single-reviewer GOV-008 finished by the original Other Models agent. It **does** preserve paid independent rendering and finishes the missing routes without buying the first half again.

---

## 1. `design_artifact_class`

**Verdict: PASS**

Recovered (`b7a20859`): `apps/web/src/design-lab/**` + `app/(design-lab)/`; MUI imports; `labNav.ts` `LeafStatus`; grep found no `fetch` / `useQuery` / `/api/v1` under `design-lab`; `/design-lab` outside `middleware.ts` auth.

Newly confirmed: live routes `/design-lab/funding`, `/market`, `/data`, `/admin`, `/reports`, `/directory` render inside the Next app with AG Grid / MUI chrome, fixture copy, no login wall.

Not standalone HTML.

---

## 2. `design_divergence`

**Verdict: PASS** (CONSULT **model identity UNVERIFIED**)

Recovered: `CONCEPTS.md` exists with alternative concepts; `FAULT_FINDINGS.md`; commercial CONSULT seed + response; Windows mojibake / timing consistent with a separate CLI process. **No invocation log of `claude -p --model …`.**

Newly: not re-opened. Not re-run.

---

## 3. `design_sameness_review`

**Verdict: PASS**

Recovered: four-state vocabulary on directory (Partly built / Data only / Planned / unmarked = works today); palette excludes substrate (Budget ledger, Competitor prices) and marks partial.

Newly: Budget ledger lens is a **Data only** panel naming `fact_budget_*` with **no placeholder chart** (`d-pf-budgets-substrate.png`). Competitor prices same pattern (`d-market-competitor-prices-substrate.png`). Listing quality is **Planned** with no figures (`d-market-quality-planned.png`). Uplift/effectiveness on planner is **"Not derived until ≥5 settled cases"** / `"—"` — not a fake KPI (`d-pf-planner-list.png`). Competitor impact `"—"` / “Not derivable; never shown as a number” (`d-market-competition.png`).

r3.1 challenged r3 (Commercial inputs removed; Promotions & Funding owns `cpor_case` lifecycle; Market & Listings is a domain). Not a copy of rejected Brief · Plan · Position · Settlement · Actions · Imports primary IA.

---

## 4. `rendered_comparison`

**Verdict: PASS** (discrepancies below are implementation ACs, not a failed design gate)

D-0008 primary domains observed on rail (desktop recovered + new; Administration on rail when role=admin):  
Overview · Stock & Sell-through · Supply & Inbound · Planning · Promotions & Funding · Market & Listings · Data & Stewardship · Administration.

“Commercial inputs” **not** found as a domain. Rejected primary vocabulary **not** used as the rail. Mobile bottom nav: Overview · Stock · Promotions · Data · More (`m-overview.png`).

Leaves and statuses match `labNav.ts` (planner partial; templates partial; budget substrate not in rail list; competitor mappings partial; competitor prices substrate; competitor listings / listing quality planned).

**Discrepancies (do not fail the design gate; bind as implementation ACs):**

| ID | Observation | Evidence |
|---|---|---|
| I1 | Planner list “Needs a decision” quotes CPR-26-1204 as **R486k**; plan workspace **Total support R369k** (est. units 1 820). List ≠ detail. | recovered casebook book R1.5m vs new `d-pf-planner-list.png` / `d-pf-plan-workspace.png` |
| I2 | Mapping 4 score **0.81**; panel “Why this score” factors 1.00×0.25 + 1.00×0.15 + 0.70×0.25 + 0.48×0.25 + 0.86×0.1 = **0.781**, while copy says “→ score 0.810”. Explanation does not reproduce the score. | `d-market-mapping-panel.png` (new) |
| I3 | OfficeWorld draft CPR-26-1202 discloses “lines and comparables shown are the CPR-26-1204 seed”, but still shows **TechMart** comparables, TechMart lineup/listings/terms, UX2780Q lines. | `d-pf-plan-officeworld.png` (new) |
| I4 | Planner lifecycle rail counts (Ended 1 · Settled 2) ≠ Case book rail (Ended 20 · Settled 6). Same lifecycle, two grains, easy to misread as one book. | recovered `d-pf-casebook.png` vs new `d-pf-planner-list.png` |
| I5 | Operator-facing “N-0010 delta” copy remains on planner export / templates (source). Not the rejected **Actions** container as primary nav, but stale node-id jargon. | `PromotionPlannerSurface.tsx` / `PlanTemplatesSurface.tsx` (source); not a rail label |

---

## 5. `content`

**Verdict: PASS**

Labels **Promotions & Funding**, **Market & Listings**, **Partly built**, **Data only**, **Planned** are consistent across recovered directory + palette and new planner/templates/market/budget/quality surfaces. Unmarked = works today.

---

## 6. `verification.rendered`

Author claims sampled. **Recovered** = `b7a20859` capture, inspected now if needed. **New** = this continuation. Match = this reviewer’s observation vs the claim.

| Claim | Observation | Screenshot | Viewport | Source | Match |
|---|---|---|---|---|---|
| C1 directory domains, 43 / 35 / 3 / 3 / 2, four-state legend, no Commercial inputs | Same counts and chips; Administration present in directory | `d-directory-full.png` | 1280 | **recovered** | yes |
| C2 case book header, lifecycle band, 5 figures, blocked reasons | Inspected `d-pf-casebook.png` after interrupt: book R1.5m, delivery 23%, Draft 1…Settled 6, blocked list | `d-pf-casebook.png` | 1280 | **recovered** (inspected now) | yes |
| C4 planner list, uplift "—", stage chips | In planning 3 · Live 1 · uplift not derived; Propose/New plan | `d-pf-planner-list.png` | 1280 | **new** | yes |
| C5 workspace CPR-26-1204: 4 lines, 1 820 units, R369k, budget 117% flagged | Same figures; TechMart params | `d-pf-plan-workspace.png` | 1280 | **new** | yes (totals vs list: I1) |
| C10 templates + mapping panel | Templates lens captured full page | `d-pf-templates.png` | 1280 | **new** | yes (representative) |
| C12 budget data only, no chart | Honest Data only panel | `d-pf-budgets-substrate.png` | 1280 | **new** | yes |
| C13 market listings, observed-only caption | “Observed only — no impact computed” | `d-market-listings.png` | 1280 | **new** | yes |
| C15 activation three outcomes | Activation lens captured | `d-market-activation.png` | 1280 | **new** | yes |
| C17 competitor mappings; impact not a number; Propose candidates disabled | Confirmed | `d-market-competition.png` | 1280 | **new** | yes |
| C18 mapping panel score explanation | Panel opens; **arithmetic ≠ 0.810** (I2) | `d-market-mapping-panel.png` | 1280 | **new** | **no** (explanation honesty) |
| C19 competitor prices data only | No chart | `d-market-competitor-prices-substrate.png` | 1280 | **new** | yes |
| C20 listing quality planned | No figures | `d-market-quality-planned.png` | 1280 | **new** | yes |
| C21 stock panel related workflows | Recovered panel; transcript found Promotion cases / Retail listings / Competitor products links | `d-stock-cover-panel.png` | 1280 | **recovered** | yes (transcript + file) |
| C22 palette “promotion”, partial marked, substrate excluded | Confirmed | `d-palette-promotion.png` | 1280 | **recovered** | yes |
| CM1 mobile planner + bottom nav | Overview · Stock · Promotions · Data · More | `m-pf-planner-list.png` | 390×844 | **new** | yes |
| CM5-class mobile listings | Listings at 390 | `m-market-listings.png` | 390×844 | **new** | yes (representative) |
| Mobile shell / overview | Domain header Overview; bottom nav D-0008 shorts | `m-overview.png` | 390×844 | **new** | yes |
| Mobile directory | Directory at 390; `scrollWidth` 375 ≤ innerWidth 390 | `m-directory.png` | 390×844 | **new** | yes |

Also **new** (required unfinished set, not all author C-rows):  
`d-pf-claims.png`, `d-pf-payments.png`, `d-data.png`, `d-reports.png`, `d-admin.png`, `d-pf-plan-officeworld.png`.

**Not recaptured (paid, preserved):** `d-overview.png`, `d-overview-figure-click.png`, `d-stock-cover-panel.png`, `d-palette-promotion.png`, `d-directory-full.png`, `d-pf-casebook.png`, `snap-d-overview.md`.

**Not independently re-walked this continuation (author claims left as recovered-or-out-of-scope):** C3 case panel CPR-26-1196; C6–C9 interaction/export/OfficeWorld mapping error state; C11, C14, C16; CM2–CM4. C9 leak **was** checked via OfficeWorld workspace (I3).

---

## 7. `verification.referent` (N-0013 ACs)

| AC | Verdict | Notes |
|---|---|---|
| high_fidelity React prototype in apps/web, fixtures, not standalone HTML | PASS | §1 |
| Architecture from source-level discovery; no assumed container count | PASS | D-0008 eight capability domains; recovered source audit |
| Materially different concepts + CONSULT with genuine model separation | PASS / UNVERIFIED model string | §2 |
| Rendered evidence 1280 every prototyped surface; 390 shell + mobile-required; claims cite screenshot+viewport | PASS as **representative independent sample** | Every surface at 1280 was **not** fully re-walked; required unfinished set + ≥3 mobile **were**. Author’s 27-capture matrix remains author-rendered. |
| D-0001/D-0003 rejected; D-0002 deferred | PASS | Rejected IA absent as primary nav; steward queue still reachable under Data |
| Production implementation blocked until operator accepts | **Operator has accepted D-0008** (ledger `acceptance_state: accepted`). This AC text is stale vs 2026-09-03 operator decision. Design gate itself: PASS |

---

## 8. Known design-lab inconsistencies (implementation ACs, not design-gate fails)

1. **List/detail totals (I1)** — CPR-26-1204 R486k vs R369k.  
2. **Score explanation (I2)** — weighted blend 0.781 vs displayed 0.81 / copy 0.810.  
3. **OfficeWorld ← TechMart seed (I3)** — disclosed, still rendered.  
4. **Planner vs case-book lifecycle counts (I4)**.  
5. **N-0010 jargon (I5)** — export/templates copy; rail is not Actions.  
6. Recovered GOV-008: concurrent **dirty production `AppShell.tsx`** while design-lab git-clean — out of prototype scope; production implementation debt.

---

## 9. Overall verdict for the design gate

**CONTENT / RENDERED MATCH: PASS**

The r3/r3.1 prototype, independently sampled (recovered Fable GOV-008 + Grok remainder), satisfies D-0008: capability-domain rail, composed overview, palette, directory, four-state honesty, Promotions & Funding as one `cpor_case` lifecycle, Market & Listings as evidence domain, no fabricated uplift/impact numbers as working analytics.

**LEDGER / INDEPENDENCE: remaining blocker — do not treat this file as a clean single-actor `gov-008` PASS that auto-completes N-0013.**

Reasons:

1. Original GOV-008 agent **did not finish** this document (usage limit).  
2. Completing reviewer is **Grok 4.6**, not the Other Models agent and not the author’s Fable 5.1.  
3. CONSULT `--model` string is still **UNVERIFIED**.  
4. Programme quality dims on N-0013 are still `authored_unverified` until a lawful `gov-008` quality record is written. This file is the evidence artifact; it is **not** a programme event.

**N-0013 `node.status → complete` is not authorised by this review alone.** Operator `acceptance_state` is already `accepted`. Completing the discovery node still requires the control plane’s independent quality gate, which this hybrid continuation does **not** silently satisfy.

---

## Operator acceptance of hybrid continuation (2026-09-03)

Operator instruction after this file existed: use the existing CONSULT skill only if the **programme/control-plane gate** genuinely requires independent adjudication; do not invent extra requirements; do not reopen architecture; do not recapture recovered GOV-008 renders.

Inspected executable gate (not CONSULT.md ladder, not this file’s caution):

- `eif_program/independence.py` `_pass_provenance_ok`: independent iff `pass_run != implementation_run` **or** `pass_actor != implementation_actor`. Model family / process / session are not fields.
- Independent dims: `rendered_comparison`, `design_sameness_review` (design_experience facet). Independent verification: `rendered` (design_experience) and `referent` (R3).
- `h_status` → `complete` also requires required quality dims in `{pass,resolved,na}`, `design_experience_ok`, operator `acceptance_state == accepted`, `verification.rendered` (ui facet), `verification.referent` (R3). Journeys: none selected for class `discovery`.
- CONSULT is **not** an event type or complete invariant. Re-running CONSULT would reopen closed IA. Not invoked.
- N-0013 had no `implementation_run` (never `node.stage` → `implement`). Independent PASS cannot evaluate until that boundary is stamped; `node.patch` cannot set it.

Operator accepted this hybrid GOV-008 (recovered Fable subagent + Grok remainder + this document) as sufficient evidence to **record** those quality/verification events. That is the compensating control for the hybrid-reviewer caveat. It does not waive the engine: `node.status complete` is still refused if provenance or required dims fail.

---

## Captures

### Recovered (do not regenerate)

`d-overview.png` · `d-overview-figure-click.png` · `d-stock-cover-panel.png` · `d-palette-promotion.png` · `d-directory-full.png` · `d-pf-casebook.png` · `snap-d-overview.md`

### New (this continuation)

`d-pf-planner-list.png` · `d-pf-plan-workspace.png` · `d-pf-plan-officeworld.png` · `d-pf-templates.png` · `d-pf-budgets-substrate.png` · `d-pf-claims.png` · `d-pf-payments.png` · `d-market-listings.png` · `d-market-activation.png` · `d-market-competition.png` · `d-market-mapping-panel.png` · `d-market-competitor-prices-substrate.png` · `d-market-quality-planned.png` · `d-data.png` · `d-reports.png` · `d-admin.png` · `m-overview.png` · `m-pf-planner-list.png` · `m-market-listings.png` · `m-directory.png`

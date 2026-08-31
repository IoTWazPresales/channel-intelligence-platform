# NS-1a independent verdict — FX display honesty and settle readiness chips

| Field | Value |
|-------|-------|
| Verifier | Opus CONSULT (independent; did not produce unit work) |
| Charter | v1.3 — only this document's **VERDICT: PASS** closes the unit |
| Branch audited | `feat/ns-1a-fx-readiness-chips` @ `5de1cf4086802ba50f87aa1bef3c65b42e9a20d8` |
| Unit commits in scope | `3e2227e`, `b973932`, `5de1cf4` |
| Evidence inputs | `docs/verify/NS1A_EVIDENCE.md` (incl. 2026-08-31 re-capture), `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 §3, `docs/design/settlement-confirm.html`, `docs/design/funding-settlement-r3.html` |
| Independent checks run | Code audit of `fxDisplay.ts`, `CporFxAnchorPanel.tsx`, `CporSettleReadinessRow.tsx`, `cpor-cases/page.tsx`, `cpor-cases/[id]/page.tsx`, `settle_readiness.py`, `pivot.py`; `pytest tests/test_cpor_settle_readiness.py` (4 passed); `vitest` `fxDisplay.test.ts` (13 passed) + `page.fxReadiness.test.tsx` (1 passed) |
| Browser re-capture | Not re-run by verifier; row rulings rely on quoted browser evidence in `NS1A_EVIDENCE.md` cross-checked against code at `5de1cf4` |

---

## 1. Contract rows NS1a-01 … NS1a-09

### NS1a-01 — Case detail anchor shows approved support in local currency with symbol (R / $)

**Ruling: SATISFIED**

**Evidence:** Browser detail case 311 — `Approved case support` `R 1,616,231.52` (`NS1A_EVIDENCE.md` §Browser detail (a)). Re-capture case 312 detail — anchor `R 0.00` under same label (`NS1A_EVIDENCE.md` §Re-capture browser case 312). Code: `CporFxAnchorPanel` renders `formatLocalMoney` with `R` prefix for ZAR (`fxDisplay.ts` `formatLocalMoney`, `CporFxAnchorPanel.tsx`).

---

### NS1a-02 — When FX declared, anchor shows USD at declared case rate + “(declared case terms)”

**Ruling: SATISFIED**

**Evidence:** Case 311 detail — `USD 97,953.43 at declared case rate ZAR 16.50 (declared case terms)` (`NS1A_EVIDENCE.md` §Browser detail (a)). Case 312 re-capture — `USD 0.00 at declared case rate ZAR 18.78 (declared case terms)` (`NS1A_EVIDENCE.md` §Re-capture). Code: `buildUsdBasisLine` + `(declared case terms)` suffix in `CporFxAnchorPanel.tsx`; `buildUsdBasisLine` returns null when FX undeclared or USD amount null (`fxDisplay.ts`).

---

### NS1a-03 — When FX undeclared, “FX undeclared” warning; USD not presented as truth

**Ruling: SATISFIED**

**Evidence:** Case 4 detail — warning `FX undeclared — USD totals are not shown as case truth until a case rate of exchange is recorded.`; no USD figure on anchor (`NS1A_EVIDENCE.md` §Browser detail (b)). Code: `CporFxAnchorPanel` shows `Alert` when `fxUndeclared`; `buildUsdBasisLine` returns null (`fxDisplay.ts` `isFxDeclared`).

---

### NS1a-04 — Readiness row with three chips matching live columns

**Ruling: SATISFIED**

**Evidence:**

| Case | DB columns (evidence file) | Chips observed |
|------|---------------------------|----------------|
| 311 | `roe_snapshot=16.5`, 0 assumption lines, `claim_rows=0` | `FX declared · 16.50` · `Assumptions clear` · `0 evidence rows` (detail + list) |
| 4 | `roe_snapshot=null`, 1 `no_cost_basis` line, `claim_rows=0` | `FX undeclared` · `1 assumption open` · `0 evidence rows` (detail + list) |
| 312 | `roe_snapshot=18.78`, 2 assumption lines, `claim_rows=0` | Same three chips on list and detail (re-capture) |

Code: `build_settle_readiness` / `load_settle_readiness_by_case_id` (`settle_readiness.py`); `buildSettleReadinessChips` (`fxDisplay.ts`); `CporSettleReadinessRow.tsx`. Detail mount is unconditional on `data.settle_readiness` presence (`page.tsx`); re-capture closes prior 312 detail collection gap.

Unit test `page.fxReadiness.test.tsx` proves anchor + readiness render for case-312 shape with assumption flags; it does **not** substitute for browser evidence on NS1a-04 (verifier accepts re-capture browser quotes).

---

### NS1a-05 — List money columns use explicit currency; USD shows “FX undeclared” when no ROE

**Ruling: SATISFIED**

**Evidence:** List search `H2-SMOKE-556` — `Ttl (local)` `—`, **`Ttl USD` `FX undeclared`** (re-capture `NS1A_EVIDENCE.md` §Browser NS1a-05). Prior capture showed `—`; fix in `5de1cf4` reordered `formatGridMoney` to test `!isFxDeclared` before null-amount return (`fxDisplay.ts` lines 123–125). `vitest` `formatGridMoney` cases confirm null USD + missing ROE → `FX undeclared`.

---

### NS1a-06 — List includes settle readiness column reflecting live case state

**Ruling: SATISFIED**

**Evidence:** Column header `Settle readiness`; cells for cases 311, 312, 4 quoted in `NS1A_EVIDENCE.md` §Browser list. Code: list column `colId: 'settle_readiness'` renders `CporSettleReadinessRow` from API `settle_readiness` (`cpor-cases/page.tsx`); list endpoint attaches `load_settle_readiness_by_case_id` (`cpor_cases.py`).

---

### NS1a-07 — USD pivot withholds grand total when `missing_roe`; states rate when declared

**Ruling: SATISFIED**

**Evidence:** Case 4 USD pivot — withheld warning, no `Grand total USD`, cell payload `{}` (`NS1A_EVIDENCE.md` §Browser detail (b)). Case 311 — `Grand total USD: $ 97,953.43 at declared case rate ZAR 16.50 (declared case terms)` (`NS1A_EVIDENCE.md` §Browser detail (a)). Code: pivot tab gates grand total on `!pivot.missing_roe` and appends rate from `data.roe_snapshot` (`page.tsx` lines 469–482).

**Note:** `missing_roe` in API/pivot is `roe_snapshot is None` only (`pivot.py` line 70, `cpor_cases.py` line 223), not `roe_snapshot == 0`. No zero-ROE case exists on this `cip` inventory (308 cases with ROE > 0; 3 null). Row NS1a-07 is evidenced for null-ROE cases only.

---

### NS1a-08 — Settlement tab repeats readiness row from API `settle_readiness`

**Ruling: SATISFIED**

**Evidence:** Case 4 Settlement tab — same three chips as detail: `FX undeclared` / `1 assumption open` / `0 evidence rows` (`NS1A_EVIDENCE.md` §Browser detail (b)). Code: Settlement panel renders `CporSettleReadinessRow` from `settlement?.settle_readiness ?? data.settle_readiness` (`page.tsx` lines 613–617); settlement payload includes `settle_readiness` from `build_settle_readiness` (`settlement.py`).

---

### NS1a-09 — Payment recon outstanding chip includes `currency_code`

**Ruling: SATISFIED**

**Evidence:** Case 311 Payments / recon — `Owed 1616231.52 ZAR`, `Paid 0.00 ZAR`, `Outstanding 1616231.52 ZAR` (`NS1A_EVIDENCE.md` §Browser detail (a)). Code: `CporPaymentEvidencePanel.tsx` labels use `` `${money(...)} ${recon.currency_code}` `` (lines 113, 119, 131).

---

## 2. FX honesty — independent code audit

### 2a. USD rendered when `roe_snapshot` is null or zero

| Surface | `roe_snapshot` null | `roe_snapshot` zero (no DB exemplar) |
|---------|---------------------|--------------------------------------|
| List `Ttl USD` | `formatGridMoney` → `FX undeclared` (no `$` value) | `isFxDeclared(0)` false → `FX undeclared` |
| Detail anchor | `fxUndeclared` alert; no `usdBasisLine` | Same (`isFxDeclared` requires `> 0`) |
| USD pivot grand total | Withheld when `pivot.missing_roe` true | **Gap:** `missing_roe` false when ROE is `0`; UI can render `Grand total USD: $ …` with rate `ZAR 0.00` (`page.tsx` 474–481, `pivot.py` 70) |
| Settlement grid `Ttl result USD` | `formatGridMoney` → `FX undeclared` | `FX undeclared` via `isFxDeclared` |

**Finding:** No violating path found for **null** ROE on evidenced surfaces. A **latent** path exists for **zero** ROE on the USD pivot grand total (API `missing_roe` semantics ≠ `fx_declared` / `isFxDeclared`). Not browser-evidenced; not represented in current `cip` data (no zero-ROE cases). Does not fail NS1a-07 as written (`missing_roe` gate).

### 2b. Converted USD without stated rate

| Surface | Declared FX behaviour |
|---------|----------------------|
| Anchor basis line | Rate in `buildUsdBasisLine` + `(declared case terms)` — **compliant** |
| Pivot grand total | Rate appended beside `formatUsdMoney` — **compliant** |
| List `Ttl USD` (declared, non-null amount) | `formatUsdMoney` only — **no inline rate** (not required by NS1a-05/07; not browser-evidenced with a non-null list USD on case 311) |
| Settlement grid `Ttl result USD` (declared) | `formatUsdMoney` only — **no per-cell rate** (outside NS1a-07 pivot scope) |

**Finding:** Primary honesty surfaces named in contract rows (anchor, undeclared withholding, pivot grand total) state rate when USD is shown. No evidenced case-row path shows a USD **value** without either withholding or an adjacent rate statement.

---

## 3. Migration and database writes

**Ruling: CONFIRMED — no migration; no writes to `cip` from this unit.**

`git diff 127f89e..5de1cf4 --name-only` touches 13 paths; none under `apps/api/alembic/`. Changed API code adds read-only `settle_readiness` derivation (`settle_readiness.py`, list/detail/settlement serializers). Evidence file states `Writes: none` on read-only queries; verifier found no INSERT/UPDATE/DELETE in unit diff.

---

## 4. Evidence chip (`0 evidence rows` / pass state)

**Population fact:** 311 / 311 `cpor_case` rows have `cpor_claim_evidence_line` count **0** (`NS1A_EVIDENCE.md` §Read-only cip inventory).

| Chip state | Adequately proven? |
|------------|-------------------|
| **Fail** — `0 evidence rows` (red) | **Yes.** Browser + DB alignment on cases 311, 4, 312; `buildSettleReadinessChips` fail branch; API `claim_evidence_count` from `load_claim_counts_by_case_id`. |
| **Pass** — `N evidence row(s)` (green, N > 0) | **No — not conclusive.** No live case with claim evidence on this database; no browser capture of pass tone. `fxDisplay.test.ts` exercises chip label logic only (mocked count); does not prove API→UI with real `cpor_claim_evidence_line` rows. |

**Impact on NS1a-04:** Row requires chips matching **live columns**; fail-tone evidence chip is fully evidenced. Pass-tone is **not required** for SATISFIED on current `cip` inventory but is **not conclusively proven** for future cases with evidence.

---

## 5. Design alignment (informational)

Readiness row matches `CIP_DESIGN_LANGUAGE.md` v1.1 §3 case/record pane ordering (anchor → readiness chips) and reference artifacts (`settlement-confirm.html`, `funding-settlement-r3.html` readiness chip pattern). Not a contract row.

---

## VERDICT: PASS

All nine contract rows NS1a-01 through NS1a-09 are **SATISFIED** with cited browser and/or code evidence at `5de1cf4`. NS1a-05 gap from initial capture is closed by `5de1cf4` and re-capture. No migration; no `cip` writes. Evidence-chip **fail** state is proven; **pass** state (N > 0) is not conclusively proven on this database but is out of scope for row satisfaction given zero claim-evidence rows everywhere.

**Residual observations (do not block PASS):** zero-ROE pivot grand-total latent path (§2a); evidence-chip pass tone unproven in live data (§4).

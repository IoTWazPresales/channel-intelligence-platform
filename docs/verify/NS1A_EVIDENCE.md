# NS-1a evidence — FX display honesty and settle readiness chips

**No PASS/FAIL verdict.** Rows below are SATISFIED / NOT SATISFIED against observed evidence only. Opus CONSULT owns PASS.

| Field | Value |
|-------|-------|
| Collection | 2026-08-30 ~23:27–00:00 UTC+2 |
| Branch | `feat/ns-1a-fx-readiness-chips` |
| Unit commit | `3e2227e935af57ea9610be125eeab95bfb686064` (`cpor: NS-1a FX display honesty and settle readiness chips`) |
| Origin | `origin/feat/ns-1a-fx-readiness-chips` at the same hash (pushed) |
| App origin | `http://127.0.0.1:3000` (origin-gated browser; serial calls) |
| Database | `cip` (printed with each read-only query) |
| Writes | none |

Tests run before the unit commit:

```
pytest tests/test_cpor_settle_readiness.py -v
4 passed in 2.38s
  test_fx_declared_requires_positive_roe PASSED
  test_count_open_assumptions_from_line_flags PASSED
  test_build_settle_readiness_shape PASSED
  test_line_with_no_cost_basis_counts_as_assumption PASSED

pnpm --filter @cip/web exec vitest run src/features/cpor/fxDisplay.test.ts
✓ src/features/cpor/fxDisplay.test.ts (11 tests)
```

---

## Read-only cip inventory

`current_database() = cip` on every query (sync engine via `app.db.session_sync`).

Population at collection:

- 311 `cpor_case` rows
- 308 with `roe_snapshot` not null and > 0
- 3 with `roe_snapshot` null (`id` 1, 3, 4)
- **311 / 311** have `cpor_claim_evidence_line` count **0** (no live case has claim evidence rows)
- 4 cases with at least one line where `distributor_id` is null or `cost_basis` is null (`id` 4, 312, 83, 84)

### Three contrast cases (quoted columns)

**(a) FX declared** — `cpor_case.id = 311`

```
id=311
case_code='C26760971'
currency_code='ZAR'
roe_snapshot='16.500000'
status='ended'
workflow_status='ended'
roe_is_null=false
claim_rows=0
line_count=18
```

Sample line (cost present, distributor present, no assumption flags):

```
cpor_case_line.id=2954 case_id=311 distributor_id=29
cost_basis='19782.7530' cost_source='historical_import'
cost_evidence_json=null flags=null
```

Expected chips from those columns: `FX declared · 16.50` · `Assumptions clear` · `0 evidence rows`.

**(b) missing_roe / no declared FX** — `cpor_case.id = 4`

```
id=4
case_code='H2-SMOKE-556'
currency_code='ZAR'
roe_snapshot=null
status='settled'
workflow_status='settled'
roe_is_null=true
claim_rows=0
```

Line:

```
cpor_case_line.id=1 case_id=4 distributor_id=1
cost_basis=null cost_source=null cost_evidence_json=null flags=null
```

(`cost_basis` null ⇒ `no_cost_basis` in settle-readiness.) Expected chips: `FX undeclared` · `1 assumption open` · `0 evidence rows`.

**(c) Open assumption flags (and zero claim rows)** — `cpor_case.id = 312`

```
id=312
case_code='C26C00003'
currency_code='ZAR'
roe_snapshot='18.780000'
status='draft'
workflow_status='draft'
roe_is_null=false
claim_rows=0
```

Line 2980 flags include `no_cost_evidence`. Line 2981 has `cost_basis=null` plus `no_cost_evidence`. Expected chips: `FX declared · 18.78` · `2 assumptions open` · `0 evidence rows`.

Other missing-ROE ids (not used as the primary (b) surface): `id=1` `C26C00001` cancelled, 0 lines; `id=3` `BATCH0-SMOKE-001` cancelled.

---

## Browser evidence (live app)

Services started with `scripts/restart-dev.ps1`. Ports 8001 and 3000 accepted TCP. List/detail were **not** captured while the page said `Loading data…`.

### List — declared FX + assumptions (page 1, id desc)

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases?page=1&page_size=50&sort_by=id&sort_dir=desc`

Quoted grid cells:

| Case | Ttl (local) | Ttl USD | Settle readiness |
|------|-------------|---------|------------------|
| C26C00003 (312) | `R 0.00` | `—` | `Readiness ✓ FX declared · 18.78 2 assumptions open 0 evidence rows` |
| C26760971 (311) | `R 1,616,231.52` | `—` | `Readiness ✓ FX declared · 16.50 Assumptions clear 0 evidence rows` |

Column headers observed: `Ttl (local)`, `Ttl USD`, `Settle readiness`. Local amounts use `R` (ZAR). No `$` figure in Ttl USD on these rows (`ttl_support_usd` is null → formatter returns `—` even when FX is declared).

### List — missing ROE (search)

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases?q=H2-SMOKE-556`  
`Page 1 / 1 ( 1 rows)`

| Case | Ttl (local) | Ttl USD | Recon | Settle readiness |
|------|-------------|---------|-------|------------------|
| H2-SMOKE-556 | `—` | `—` | `owed_unknown` | `Readiness FX undeclared 1 assumption open 0 evidence rows` |

Ttl USD is `—`, not the literal string `FX undeclared`. No dollar amount is shown.

Portfolio intelligence on the list still shows USD headings (`$1,623,915`, `Planned: $181,669`). That is a **portfolio** surface, not the case-row honesty path. Not scored as NS1a case-row evidence.

### Detail (a) — id 311 / C26760971

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases/311`

Quoted:

- Status: `ended` · `workflow: ended` · `v1`
- Readiness: `FX declared · 16.50` · `Assumptions clear` · `0 evidence rows`
- Metadata: `CUST-000012 — Takealot · Sell out PP · 2026-07-30 → 2026-08-31 · ZAR`
- Anchor: **Approved case support** `R 1,616,231.52`
- Basis: `USD 97,953.43 at declared case rate ZAR 16.50 (declared case terms)`
- USD pivot tab: `Grand total USD: $ 97,953.43 at declared case rate ZAR 16.50 (declared case terms)`
- Payments / recon chips: `Owed 1616231.52 ZAR` · `Paid 0.00 ZAR` · `Outstanding 1616231.52 ZAR` plus status `outstanding`
- Empty-state: `No payment / CN evidence for this case.`

### Detail (b) — id 4 / H2-SMOKE-556

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases/4`

Quoted:

- Chips: `settled` · `workflow: settled` · `v1` · **`missing_roe`** · `no_cost_basis`
- Readiness: **`FX undeclared`** · **`1 assumption open`** · **`0 evidence rows`**
- Metadata: `CUST-1001 — Metro Market Group · Sell out PP · 2026-01-01 → 2026-01-31 · ZAR`
- Anchor warning: `FX undeclared — USD totals are not shown as case truth until a case rate of exchange is recorded.`
- No USD amount on the anchor.
- USD pivot (tab selected): `FX undeclared — USD pivot totals are withheld until a case rate of exchange is recorded.` Cell payload `{}`. **No** `Grand total USD` heading.
- Settlement tab: claim-evidence copy + **the same three readiness chips repeated** at the bottom of the panel.

### Detail (c) — id 312 / C26C00003

List row (above) shows the three chips matching the queried columns.

Detail URL `http://127.0.0.1:3000/commercial-planner/cpor-cases/312` after load:

- Heading `C26C00003`
- Flag chips include `no_cost_basis`, `no_cost_evidence` (matches line `cost_evidence_json.flags`)
- Subtitle includes `ROE 18.78`
- Line flags quoted: `no_soh_evidence, no_cst_mac, no_intake_evidence, dsi_wac_not_ingested, disti_cost_is_intake_proxy, no_cost_evidence` and a second line starting `no_cost_basis, …`

**Gap:** accessibility snapshot and screenshots of this detail page did **not** show `CporFxAnchorPanel` (“Approved case support”) or the `READINESS` chip row, even though the same page component rendered both on ids 311 and 4. Line header on this detail still reads `Ttl ZAR` (list uses `Ttl (local)`).

---

## Contract rows NS1a-01 … NS1a-09

Source: NS-1a unit contract from the FX-display CONSULT (Grammar 1). **Not a PASS of the unit.**

| Row | Requirement | Status | Evidence |
|-----|-------------|--------|----------|
| NS1a-01 | Case detail anchor shows approved support in local currency with symbol (R / $) | **SATISFIED** | 311: `R 1,616,231.52` under “Approved case support”. (312 detail did not show the anchor; 311 is the declared-FX exemplar.) |
| NS1a-02 | When FX declared, anchor shows USD at declared case rate + “(declared case terms)” | **SATISFIED** | 311: `USD 97,953.43 at declared case rate ZAR 16.50 (declared case terms)` |
| NS1a-03 | When FX undeclared, “FX undeclared” warning; USD not presented as truth | **SATISFIED** | 4: warning `FX undeclared — USD totals are not shown as case truth…`; no USD figure on the anchor |
| NS1a-04 | Readiness row with three chips matching live columns | **SATISFIED** | 311 chips match `roe_snapshot=16.5`, 0 assumption lines, `claim_rows=0`. 4 chips match `roe_snapshot=null`, 1 `no_cost_basis` line, `claim_rows=0`. 312 **list** chips match `18.78` / 2 assumption lines / 0 claims |
| NS1a-05 | List money columns use explicit currency; USD shows “FX undeclared” when no ROE | **NOT SATISFIED** | Local column uses `R` / `Ttl (local)` (good). For H2-SMOKE-556, **Ttl USD cell is `—`**, not the string `FX undeclared`. Cause: `formatGridMoney` returns `—` when the USD amount is null **before** the undeclared-FX branch. Honesty (no fake `$` value) holds; the contracted label does not appear in that cell |
| NS1a-06 | List includes settle readiness column reflecting live case state | **SATISFIED** | Column `Settle readiness` on the grid; cells quoted above for 311/312/4 match cip columns |
| NS1a-07 | USD pivot withholds grand total when `missing_roe`; states rate when declared | **SATISFIED** | 4: withheld warning, no `Grand total USD`. 311: `Grand total USD: $ 97,953.43 at declared case rate ZAR 16.50 (declared case terms)` |
| NS1a-08 | Settlement tab repeats readiness row from API `settle_readiness` | **SATISFIED** | 4 Settlement tab repeats `FX undeclared` / `1 assumption open` / `0 evidence rows` |
| NS1a-09 | Payment recon outstanding chip includes `currency_code` | **SATISFIED** | 311 Payments / recon: `Owed 1616231.52 ZAR`, `Paid 0.00 ZAR`, `Outstanding 1616231.52 ZAR` |

---

## Notes for CONSULT (not verdicts)

- Every case on this `cip` has **zero** claim-evidence rows, so the evidence chip cannot be demonstrated in the `N evidence rows` pass state from live data.
- List Ttl USD is `—` on declared-FX rows when `ttl_support_usd` is null (311 still shows USD on the **detail** anchor/pivot from a populated USD total).
- Workspace was switched off this branch twice during the session (`docs/eif-unit-declaration`); evidence was captured against the running tree that served NS-1a UI on 311/4/list, then this file was written after checking `feat/ns-1a-fx-readiness-chips` back out at `3e2227e`.

---

## Re-capture — NS1a-05 fix + case 312 detail (2026-08-31)

**No PASS/FAIL verdict.** Supplements rows NS1a-05 and case 312 detail only; prior sections unchanged.

| Field | Value |
|-------|-------|
| Collection | 2026-08-31 ~08:50 UTC+2 |
| Branch | `feat/ns-1a-fx-readiness-chips` |
| Base commit (pre-fix) | `b97393291419b83ad08b3e0075cfc8489000673d` |
| App origin | `http://127.0.0.1:3000` (browser automation; API warm via `scripts/restart-dev.ps1`) |
| Database | `cip` (`current_database() = cip`) |
| Writes | none |

### Fixes applied

**NS1a-05 — `formatGridMoney` ordering:** For `kind === 'usd'`, check `!isFxDeclared(...)` **before** the null-amount early return so undeclared-FX rows emit `FX undeclared` even when `ttl_support_usd` is null; declared-FX rows with null amount still emit `—`.

**Case 312 detail — render conditions (no code change):**

- **FX anchor panel:** unconditional — always mounts `<CporFxAnchorPanel … />` once case data has loaded (`page.tsx` after the loading gate).
- **Readiness row:** `{data.settle_readiness ? ( <CporSettleReadinessRow … /> ) : null}` — gated only on API `settle_readiness` presence, **not** on assumption flags.

Original gap was a **collection artifact** (list captured while grid still loading; detail captured mid-session after branch switches per note above). Warm re-capture below shows both surfaces on id 312 with assumption flags present. Regression test added: `page.fxReadiness.test.tsx`.

### Tests (post-fix)

```
pytest tests/test_cpor_settle_readiness.py -v
4 passed in 2.86s

pnpm --filter @cip/web exec vitest run src/features/cpor/fxDisplay.test.ts \
  "src/app/(app)/commercial-planner/cpor-cases/[id]/page.fxReadiness.test.tsx"
✓ fxDisplay.test.ts (13 tests)
✓ page.fxReadiness.test.tsx (1 test)
```

### Browser — NS1a-05 list (H2-SMOKE-556)

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases?q=H2-SMOKE-556`  
Grid loaded after API warm (`Page 1 / 1 ( 1 rows)`).

| Case | Ttl (local) | Ttl USD | Settle readiness |
|------|-------------|---------|------------------|
| H2-SMOKE-556 | `—` | **`FX undeclared`** | `Readiness FX undeclared 1 assumption open 0 evidence rows` |

Prior capture showed Ttl USD `—`; post-fix cell is the literal string **`FX undeclared`**.

### Browser — case 312 detail (C26C00003)

URL: `http://127.0.0.1:3000/commercial-planner/cpor-cases/312`  
After full load (no `Loading…`):

- Flag chips include `no_cost_basis`, `no_cost_evidence`, `no_cst_mac`, …
- **Readiness:** `FX declared · 18.78` · `2 assumptions open` · `0 evidence rows`
- **Anchor:** **Approved case support** `R 0.00`
- Basis: `USD 0.00 at declared case rate ZAR 18.78 (declared case terms)`

### Updated contract status (re-capture rows only)

| Row | Requirement | Status | Evidence |
|-----|-------------|--------|----------|
| NS1a-05 | List money columns use explicit currency; USD shows “FX undeclared” when no ROE | **SATISFIED** | H2-SMOKE-556 Ttl USD cell = `FX undeclared` (not `—`) after `formatGridMoney` ordering fix |
| NS1a-04 (312 detail supplement) | Readiness row on detail matches live columns | **SATISFIED** | 312 detail readiness chips + anchor quoted above; prior detail gap was collection timing, not assumption-flag conditional |

---

## KNOWN EVIDENCE GAP

The readiness **evidence chip pass state** (`N evidence row(s)`, green tone when `claim_evidence_count > 0`) is **unproven on live data** on this `cip` database: all 311 `cpor_case` rows have zero `cpor_claim_evidence_line` rows (see §Read-only cip inventory). Only the **fail** state (`0 evidence rows`) is browser-evidenced. Unit tests (`fxDisplay.test.ts`) cover pass/fail label logic with mocked counts only — not API→UI with real claim evidence.

**Re-evidence trigger:** when any case on `cip` has one or more claim-evidence rows, capture list + detail readiness chips showing the pass-tone evidence chip and confirm the count matches `load_claim_counts_by_case_id`.

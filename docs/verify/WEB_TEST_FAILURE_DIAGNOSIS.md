# Web test failure diagnosis — Session B (`pnpm test:web`)

**Date:** 2026-08-30  
**Branch:** `docs/verify-debt-runbook` @ `cfe8ef8` (Session B evidence)  
**Scope:** Read-only diagnosis of **20 failures** from Session B Unit 12 `pnpm test:web` run  
**Excluded:** No product-source or test changes in this session.

**Summary:** 19/20 failures share one **test-harness** root cause on the imports page (upload mutation never succeeds in vitest). 1/20 is a **separate, flaky** customers drawer test. **Product regression is not supported** for historical_lineup apply/mapping in current source.

---

## Session B failure inventory

| File | Failed | Passed (file) | Primary error |
|------|--------|---------------|---------------|
| `apps/web/src/app/(app)/admin/imports/page.test.tsx` | 19 | 7 | `Unable to find role="button" and name /Apply validated file/i` (and downstream: mapping review, quality review, diagnostic chips, loaded lineup) |
| `apps/web/src/app/(app)/admin/customers/page.test.tsx` | 1 | 13 (file) | `Test timed out in 5000ms` on `findAllByLabelText('Location code')` |

Full-suite evidence: `apps/api/.tmp_session_b_unit12_vitest_all.txt` (local, not committed).  
Focused re-run (this session): `pnpm test:web -- "src/app/(app)/admin/imports/page.test.tsx"` → **19 failed | 7 passed (26)**.

---

## 1. When did `admin/imports/page.test.tsx` start failing?

### Git history (test file + product surface)

```
a90f191 web: align owning-route PageHeader chrome with nav
60dc5a7 import: BACKLOG-027 PM/HL mount shared CanonicalColumnMappingPanel   ← Unit 11
5b55c81 imports: sync PM wizard activeStep from server job state
…
f47bcea feat(historical-lineup): Phase 3C import quality review panel
0d6f50d fix(imports): clear Apply button gate and add success Alert after historical_lineup apply
```

### Introducing regression (static evidence — high confidence)

| Commit | Date | Change relevant to tests |
|--------|------|---------------------------|
| `60dc5a7` | 2026-08-12 | Unit 11: HL mapping → `CanonicalColumnMappingPanel`; **tests updated** (`hl-map-*` test ids). Upload/apply UX unchanged in intent. |
| `5b2a6a4` | 2026-08-20 | `rbac: stamp CPOR write actors` — **`upload` mutation** (and other fetch paths) switched from in-component `defaultHeaders` to **`authHeaders()` from `@/lib/api`**. |
| `5b2a6a4^` = `4ea1782` | 2026-08-20 | Last commit **before** `authHeaders` on the generic upload path. |

**Before `5b2a6a4`** (`4ea1782`), upload used local headers:

```typescript
const res = await fetch(apiUrl('/api/v1/imports/jobs'), {
  method: 'POST',
  body: fd,
  headers: defaultHeaders,
});
```

**At HEAD** (`page.tsx` ~1880–1884):

```typescript
const res = await fetch(apiUrl('/api/v1/imports/jobs'), {
  method: 'POST',
  body: fd,
  headers: authHeaders(undefined, false),
});
```

**Test mock** (`page.test.tsx` ~156–185) exports `apiGet`, `apiUrl`, `readFetchError`, `safeDisplayError` only — **no `authHeaders`**.  
`vi.mock('@/lib/api', …)` replaces the whole module, so `authHeaders` is `undefined` and the mutation throws before `global.fetch` runs.

### Bisect / rerun attempts (this session)

| Attempt | Result |
|---------|--------|
| HEAD, file-only `pnpm test:web -- imports/page.test.tsx` | **19 failed \| 7 passed** (reproducible) |
| Checkout `page.tsx` + `page.test.tsx` at `5b55c81` on HEAD tree | Vitest **collect failed** (`no tests`) — incomplete tree (missing pre-Unit-11 modules). |
| Checkout `page.tsx` at `5b55c81` with HEAD `CanonicalColumnMappingPanel` | **19 failed \| 7 passed** — inconsistent tree; not valid bisect. |
| Git worktree at `5b55c81` (`.wt-bisect-5b55c81/`) | Worktree created; vitest could not be executed from worktree in this environment (no local `node_modules` symlink). |

**Inferred last green commit for HL vitest clusters:** **`4ea1782`** (`5b2a6a4^`) — last revision where upload did not depend on a mocked `authHeaders`.  
**Empirical confirmation still recommended:** checkout `4ea1782`, run `pnpm test:web -- "src/app/(app)/admin/imports/page.test.tsx"`, expect HL clusters to pass (7 passing tests today should remain passing).

**Note on Unit 11:** `60dc5a7` predates `5b2a6a4`. Panel/test-id changes at Unit 11 are not the primary break; the **`authHeaders` mock gap at `5b2a6a4`** explains all upload-dependent failures at HEAD.

---

## 2. Imports failures — per cluster

**Shared mechanism:** Tests mock `global.fetch` for POST `/api/v1/imports/jobs`, but the upload mutation never reaches `fetch` because `authHeaders` is undefined. Therefore:

- `upload.isSuccess` stays false  
- `historicalValidatedJobId` is never set in `onSuccess`  
- UI gated on validate success never renders (Apply, mapping review header, quality review, diagnostics, loaded lineup)

**Passing tests (7):** deferred-template visibility (2), `?job=` revisit (3), mapping panel absent before upload (1), DSI guidance copy (1) — none require a successful HL upload mutation.

### Cluster A — Apply button post-success (3 tests)

| Test | Failing assertion |
|------|-------------------|
| `Apply button appears after validate succeeds and a file is present` | `expect(await screen.findByRole('button', { name: /Apply validated file/i })).toBeInTheDocument()` |
| `Apply button disappears and apply success Alert appears after apply succeeds` | Same + `apply-success-alert` |
| `validate success Alert shows generic message…` | `findByRole('button', { name: /Refresh validation preview/i })` |

**Product source that should satisfy (HEAD):** Apply affordance exists when `historical_lineup` + `historicalValidatedJobId != null` + `lastGenericFile`:

```4586:4640:apps/web/src/app/(app)/admin/imports/page.tsx
            {selectedTemplate?.slug === 'historical_lineup' && historicalValidatedJobId != null && lastGenericFile ? (
              …
                  <Button …>
                    Apply validated file
                  </Button>
```

`onSuccess` sets `historicalValidatedJobId` when `data.import_mode === 'validate'` (~1893–1895).

| Verdict | **STALE TEST** (mock incomplete after `5b2a6a4`) |
| Fix owner | **Test change** — extend `@/lib/api` mock with `authHeaders` (or `importOriginal` partial mock). Not a product fix. |

---

### Cluster B — Mapping review panel (5 tests; 1 passes)

| Test | Failing assertion (typical) |
|------|----------------------------|
| `mapping review panel appears and shows source columns after validate` | `findByText(/Column mapping review/i)` |
| `re-validate with corrections sends mapping_override…` | Same + `hl-map-Customer` |
| `apply with edits sends mapping_override…` | Same + Apply button |
| `start over clears the mapping review panel` | Mapping review visible then cleared |
| `mapping review panel is absent before validate completes` | **Passes** — no upload |

**Product source:** Panel renders when `historicalValidatedJobId != null && hlSheetDetail` (~4454–4488), using `CanonicalColumnMappingPanel` with `testIdPrefix="hl"`.

| Verdict | **STALE TEST** — blocked on upload; not a Unit 11 panel regression in product |
| Fix owner | **Test change** (authHeaders mock first; `hl-map-*` ids already match `CanonicalColumnMappingPanel`) |

---

### Cluster C — Phase 3B mapping label clarity (3 tests)

| Test | Failing assertion |
|------|-------------------|
| `mapping review shows "Product identity (SKU)" label not bare "SKU"` | `findByText(/Column mapping review/i)` then label text |
| `mapping review shows "Base unit (descriptor)" as a target option` | Open `hl-map-*` target options |
| `regression: sku_raw stays unmapped…` | Mapping panel after validate |

| Verdict | **STALE TEST** (upload gate) |
| Fix owner | **Test change** |

---

### Cluster D — Phase 3B diagnostic summary chips (1 test)

| Test | Failing assertion |
|------|-------------------|
| `diagnostic summary chips appear with code counts…` | `findByTestId('diagnostic-summary')` |

Requires validate job rows + successful upload.

| Verdict | **STALE TEST** |
| Fix owner | **Test change** |

---

### Cluster E — Phase 3C quality review panel (3 tests)

| Test | Failing assertion |
|------|-------------------|
| `quality review panel shows apply-ready badge…` | `findByTestId('quality-review-badge')` |
| `quality review panel groups unknown customer tokens…` | `findByTestId('quality-review-panel')` |
| `apply button shows inline confirmation when unresolved customers exist…` | `findByRole('button', { name: /Apply validated file/i })` |

| Verdict | **STALE TEST** |
| Fix owner | **Test change** |

---

### Cluster F — Sub-pass A loaded lineup records (5 tests)

| Test | Failing assertion |
|------|-------------------|
| `loaded lineup section appears after apply and shows line data` | Apply + lineup section |
| `loaded lineup section shows empty state…` | Apply + empty state |
| `View apply job link appears in success alert…` | Apply + `view-apply-job-link` |
| `unresolved customer token chips appear…` | Apply + chips |
| `unresolved customer token section is absent…` | Apply flow |

| Verdict | **STALE TEST** |
| Fix owner | **Test change** |

---

## 3. Customers drawer timeout (separate cluster)

| Test | Error |
|------|-------|
| `submits add location and add contact from drawer` | `Test timed out in 5000ms` at `findAllByLabelText('Location code')` (~line 308) |

**Not bundled with imports.** Product drawer and labels are unchanged in intent:

- Drawer opens via `MasterDataGridShell` `drawer` prop (~1142–1147).  
- Location fields use `label="Location code"` (~1218, 1286).  
- Submit button: `Add location` (~1317).

**Sibling test passes at HEAD:** `renders drawer locations and contacts sections` waits for `Locations` and `LOC-001` before asserting.

**Re-run this session (isolated file):**

```text
pnpm test:web -- "src/app/(app)/admin/customers/page.test.tsx" -t "submits add location"
→ PASSED in ~1.8s (full file 14/14 passed)
```

| Verdict | **STALE TEST (flaky / suite-order timing)** — fails at 5000ms under full `pnpm test:web` (545 tests), passes in isolation |
| Fix owner | **Test change** — e.g. `await screen.findByText('Locations')` before `findAllByLabelText`, `waitFor` on location query, or raise timeout for drawer mutations; not a product bug on current evidence |
| Ambiguity | If full-suite flake persists after harness fix, profile test order pollution (no evidence of product regression) |

---

## 4. Does “Apply validated file” exist today? Can operators still apply?

### In product source — **yes**

The button label **“Apply validated file”** is present at HEAD (`page.tsx` ~4639). Step 3 copy also references it (~3029–3030).

**Render gate:** `historical_lineup` + `historicalValidatedJobId != null` + `lastGenericFile` (and optional unknown-customer confirm branch ~4587–4617).

### Operator path (live UI — not vitest)

1. **Import Center** → select **Historical Lineup** template.  
2. Wizard: **Next** through provider (skipped when not required) → column expectations → import mode (locked to validate).  
3. **Upload step:** choose file → validate job runs (`import_mode=validate`).  
4. Review **column mapping** / **quality review** when job detail loads.  
5. Click **Apply validated file** (or **Apply anyway** after unknown-customer confirm).  
6. Second POST runs with `import_mode=apply` (+ optional `mapping_override`).

**Conclusion:** Operators can still apply a validated historical lineup file via the explicit second-click Apply control. Session B failures do **not** indicate removal of that affordance; they indicate the **test mock does not execute the upload mutation**.

---

## 5. Recommended fix owners (summary)

| Cluster | Count | Verdict | Fix owner |
|---------|-------|---------|-----------|
| Imports A–F (HL upload-dependent) | 19 | STALE TEST (`authHeaders` mock gap since `5b2a6a4`) | **Test** — add `authHeaders` to `page.test.tsx` api mock (or partial mock) |
| Customers drawer submit | 1 | STALE TEST (flaky under full suite) | **Test** — stabilize waits/timeout |
| Product HL apply/mapping | — | No regression evidenced | **None** for these failures |

---

## 6. Commands used (evidence)

```text
pnpm test:web -- "src/app/(app)/admin/imports/page.test.tsx"
# → Test Files 1 failed | Tests 19 failed | 7 passed (26)

pnpm test:web -- "src/app/(app)/admin/customers/page.test.tsx"
# → Test Files 1 passed | Tests 14 passed (14)

git log --oneline -15 -- apps/web/src/app/(app)/admin/imports/page.test.tsx
git show 5b2a6a4 -- apps/web/src/app/(app)/admin/imports/page.tsx  # authHeaders introduction
git show 5b2a6a4^:apps/web/src/app/(app)/admin/imports/page.tsx  # defaultHeaders upload
```

---

**Diagnosis only.** No `VERDICT: PASS` — Opus VERIFY remains required for Unit 12 web row after harness fixes.

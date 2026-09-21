# Density proposal — operator data scale (comfortable)

**Date:** 2026-09-21
**Branch:** `feat/ns-2-brief-nav-collapse`
**Lab render:** `/design-lab/density` (`b0c0112`)
**Status:** **PROPOSAL ONLY — NOT SHIPPED.** No production value was changed. Do
not treat this doc as a change record.

---

## 1. The proposal

One change, three values, isolated so the delta is attributable:

| Value | Current | Proposed |
|-------|---------|----------|
| Grid row height | 42px | **36px** |
| Grid header height | 42px | **36px** |
| Grid type size | 14px (`0.875rem`) | **13px (`0.8125rem`)** |

Panel padding, headline figures, controls, rail width and page chrome are
**unchanged**, and are rendered at current values in both frames of the lab so
the only variable is the grid itself.

This is deliberately *not* "add a density mode". A density axis already exists
(§4). The proposal is to change **what `comfortable` means**.

---

## 2. Evidence

Rendered at 1280×800 with the 252px `AppShell` rail reserved, so content width is
honest. Both frames use the same 540px grid height and the same 60 sample rows.
Verified in the browser at `/design-lab/density`, not computed from the source.

### 2.1 Rows visible: 11 → 14 (+27%)

| Frame | Arithmetic | Rows |
|-------|-----------|------|
| Current | `floor((540 − 42) / 42)` | **11** |
| Proposed | `floor((540 − 36) / 36)` | **14** |

+3 rows, **+27%** more of the dataset in the same viewport, with no layout
change anywhere else on the page. On a 540px grid that is the difference between
seeing a third of a 40-line shipment case and seeing nearly half of it without
scrolling.

### 2.2 The product column stops truncating

This is the finding that matters more than the row count, because it is a
correctness-of-reading issue rather than a comfort one.

At **14px**, the `Product (sales model)` column (`minWidth 170, flex 1.4`)
truncates the sales model on most rows:

```
S5452MA-I716512S…      FA506NCG-78512B…
H7607BA-ON12810…       GX651AX-U96420G…
```

At **13px**, every sample sales model renders in full:

```
S5452MA-I716512S0W     FA506NCG-78512B0W
H7607BA-ON12810B0X     GX651AX-U96420G0W
X1652DA-516512S0W
```

A truncated ASUS sales model is not a cosmetic loss. The distinguishing
characters sit at the **end** of the string — `...512S0W` vs `...810B0X` vs
`...420G0W` encode configuration. `S5452MA-I716512S…` and a sibling SKU can
render identically while being different products. An operator reading the
current grid has to hover or widen to tell two lines apart.

Two column **headers** also stop truncating at 13px, which was not part of the
original claim but is visible in the same render:

| Header | At 14px | At 13px |
|--------|---------|---------|
| `Product (sales model)` | `Product (sales mo…` | full |
| `Channel partner` | `Channel part…` | full |

Still truncating at 13px: `Incredible Conne…` in the channel-partner column.
13px narrows the problem; it does not eliminate it.

---

## 3. Where the values actually live

**In `apps/web`, inside `change_paths`. `packages/ui` is not where it lives.**
This matters because `packages/ui` *also* emits density variables, and editing
them would appear to work while changing nothing.

### 3.1 Row and header height — `apps/web`, authoritative

`apps/web/src/components/EnterpriseDataGrid.tsx:121-122`:

```tsx
headerHeight={theme.density === 'compact' ? 36 : 42}
rowHeight={theme.density === 'compact' ? 34 : 42}
```

These are explicit `AgGridReact` props and they **win** over any CSS variable.
`packages/ui/src/agGridMuiTheme.ts:78-79` emits `--ag-row-height` and
`--ag-header-height` with the same numbers, but for height purposes that emission
is **dead** — overridden on every mount. Changing it alone would do nothing.

Note the prop order: `headerHeight`/`rowHeight` are spread *before*
`{...restGridOptions}`, so a caller's `gridOptions.rowHeight` overrides the theme
default. That is the seam the lab render uses, and the seam any staged rollout
would use.

### 3.2 Grid type size — `apps/web/src/theme/cipTheme.ts`

The chain is:

```
cipTheme.ts  →  theme.typography.body2.fontSize
             →  packages/ui/src/agGridMuiTheme.ts:25
             →  --ag-font-size
```

`agGridMuiTheme.ts:25` reads:

```ts
const fontSize = typeof theme.typography.body2?.fontSize === 'string'
  ? theme.typography.body2.fontSize
  : '0.8125rem';
```

`cipTheme.ts:34` sets `body2: { color: t.text.secondary }` with **no
`fontSize`** — so MUI's `createTheme` fills in its default `0.875rem`, the
`typeof === 'string'` test passes, and the grid renders at 14px. The `0.8125rem`
fallback is *already the proposed value* and is **never reached**.

So the change point for grid type is `cipTheme.ts`, in `change_paths`. Which
leads directly to the problem in §5.1.

---

## 4. A density axis already exists — and the proposal collides with it

`cipTheme.ts:8-22` declares `density: 'comfortable' | 'compact'`, with
`spacingFactor` 1 vs 0.85. It is **user-facing today**:

- `features/shell/AppShell.tsx:243-247` — a toolbar toggle ("compact rows" icon)
- `app/(app)/settings/page.tsx:204-208` — "Table density", reads the store
- `stores/uiStore.ts:10` — persisted preference
- `app/providers.tsx:18` — feeds `CipThemeProvider`

Current tiers, and where the proposal lands:

| Tier | Row | Header |
|------|-----|--------|
| `comfortable` (today) | 42 | 42 |
| **proposed `comfortable`** | **36** | **36** |
| `compact` (today) | 34 | 36 |

**The proposed comfortable sits 2px from the existing compact.** Header heights
become identical (36 = 36). A user toggling density would see a 2px row change
and no header change — a control that appears broken.

This is the main unresolved design question, and it is not answered by the lab
render. Three ways out, none free:

1. **Collapse to one tier.** Drop the toggle, ship 36/36 for everyone. Removes a
   shipped, persisted, discoverable preference.
2. **Re-space both tiers.** e.g. comfortable 36/36, compact 30/32. Changes what
   compact means for users who already chose it, and 30px rows need a check
   against the Inter line-height before anyone claims they are legible.
3. **Leave compact alone, accept the 2px gap.** Cheapest; leaves a control whose
   effect is imperceptible, which is worse than no control.

No recommendation is made here — this is Warren's call, and it should be made
before any code, not discovered during a rollout.

---

## 5. What shipping would actually require

### 5.1 The type change is not scoped to grids

Setting `body2.fontSize = '0.8125rem'` in `cipTheme.ts` is a one-line edit that
reaches **far** past the grid. In `apps/web/src` there are:

- **721** `variant="body2"` usages
- **570** `variant="caption"` usages (caption inherits nothing from body2, but
  sits next to it everywhere and would then look proportionally large)

So the one-line version silently shrinks every secondary paragraph, helper text,
panel description and `ModuleDataSection` empty-state body in the app. That is a
whole-app typography change wearing a grid change's clothes, and it is **not**
what the lab render shows: the lab scoped the change by overriding
`--ag-font-size` inline on `.ag-root-wrapper`, touching only the grid.

Two honest options:

- **(a) Grid-scoped token.** Add a dedicated grid type token and have
  `agGridMuiTheme.ts:25` read *that* instead of `body2.fontSize`. Keeps the blast
  radius at the grid. Requires a `packages/ui` change, so it is no longer an
  `apps/web`-only edit.
- **(b) Set it in `EnterpriseDataGrid`'s `shellSx`.** Stays inside `apps/web` and
  `change_paths`, at the cost of the value living in a component rather than the
  theme — which is how it ends up duplicated, per §5.2.

**(a) is the right answer** for a value that is part of the design language. It
just is not the cheap answer, and the cheap answer is the one that would get
reached for under time pressure.

### 5.2 The four numbers live in three places

| Location | Values |
|----------|--------|
| `apps/web/src/components/EnterpriseDataGrid.tsx:121-122` | 42/42, 34/36 — hard-coded inline |
| `apps/web/src/features/plan-vs-executed/gridPagination.ts:7-10` | `STANDARD_ROW_HEIGHT` 42, `COMPACT_ROW_HEIGHT` 34, `STANDARD_HEADER_HEIGHT` 42, `COMPACT_HEADER_HEIGHT` 36 |
| `packages/ui/src/agGridMuiTheme.ts:78-79` | `--ag-row-height` 34/42, `--ag-header-height` 36/42 (dead for height, §3.1) |

`gridPagination.ts:6` already carries the warning in a comment: *"must match
EnterpriseDataGrid default (42) and gridOptions.rowHeight"* — a comment where a
shared constant should be.

`gridPagination`'s constants are not decorative. `paginatedGridHeight()` computes
shell height as `header + row × pageSize + 48`, and `ExceptionCategoryGrid:142`
and `PlanVsExecutedView:461,474` size themselves from `gridRowMetrics()`.
**Changing only `EnterpriseDataGrid` would leave every paginated grid sized for
42px rows while rendering 36px rows** — a growing strip of dead space above the
pagination bar on plan-vs-executed and the exception grids.

So step one of shipping is not a density change at all. It is: **make these one
source of truth**, then change that one number. That refactor is the prerequisite
and should be a separate unit.

---

## 6. Risks and what to check before shipping

| Risk | Check |
|------|-------|
| **Row-height coupling** (§5.2) | Every `paginatedGridHeight()` caller re-measured, not just spot-checked |
| **`autoHeight` / `wrapText` columns** | The settlement-desk Corroboration column is `width 188 / wrapText / autoHeight`. Wrapped cells derive height from content, not `rowHeight` — a 36px baseline beside a 3-line wrapped cell may read worse, not better |
| **Touch targets** | In-grid action buttons (`cst-alias-edit/confirm/reject`, planner row actions) sit in the row box. A 36px row leaves little vertical room; check against the 390px mobile workflows DIRECTION §6 names |
| **13px legibility** | 13px Inter on the dark theme at `text.secondary` contrast — verify against WCAG, not by eye. Dark-mode small type at reduced contrast is where this most plausibly fails |
| **`body2` blast radius** (§5.1) | If option (b) is taken, confirm no grid-adjacent caption now looks oversized |
| **Density-toggle collapse** (§4) | Whatever tier decision is made, the toolbar toggle must produce a visible change or be removed |

None of these are blockers. All of them are reasons this is a proposal and not a
patch.

---

## 7. Recommendation

The evidence for the change is good, and stronger on legibility than on density:
**+27% rows is the headline, but the untruncated sales model is the real
argument.** Truncation that hides the distinguishing characters of a SKU is a
correctness problem in a tool whose job is telling SKUs apart.

But the change is not the three-value edit it looks like. Ordered:

1. **Warren decides the density-tier question** (§4). Everything else is
   downstream of it.
2. **Unify the four height values** into one source of truth (§5.2). Separate
   unit, no behaviour change, independently verifiable.
3. **Add a grid-scoped type token** (§5.1 option a) so 13px reaches the grid and
   nothing else.
4. **Then** change the numbers, and smoke the surfaces in §6 — including a
   `wrapText`/`autoHeight` grid and a paginated grid, which the lab render does
   not cover.

Shipping steps 2 and 3 is worthwhile **whether or not the density change is ever
made**: today four numbers are duplicated across three files with a comment
standing in for a constant, and a whole-app typography token is doing a grid's
job. That is true independently of density.

**Not shipped. No production value changed by this doc or by `b0c0112`.**

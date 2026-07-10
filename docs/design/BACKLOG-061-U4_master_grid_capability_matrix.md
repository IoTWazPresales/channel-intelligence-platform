# BACKLOG-061 U-G1 — Master grid capability matrix

**Unit:** U-G1 (docs-only)  
**Purpose:** Compare admin Customers / Products / Distributors master grids before extracting `MasterDataGridShell` (U-G2).  
**Review gate:** This doc must be reviewed before U-G2 implementation.  
**Scope:** Docs only — no app code changes in this unit.

**Sources (read for this matrix):**

| Surface | Path |
|---------|------|
| Customers page | `apps/web/src/app/(app)/admin/customers/page.tsx` |
| Products page | `apps/web/src/app/(app)/admin/products/page.tsx` |
| Distributors page | `apps/web/src/app/(app)/admin/distributors/page.tsx` |
| Grid wrapper | `apps/web/src/components/EnterpriseDataGrid.tsx` |
| Bulk selection toolbar | `apps/web/src/components/bulkTable/BulkSelectionToolbar.tsx` |
| Bulk delete impact dialog | `apps/web/src/components/bulkTable/MasterBulkDeleteImpactDialog.tsx` |
| Row delete column helper | `apps/web/src/components/gridDeleteColumn.tsx` |
| Commercial-planner column modal (non-regression anchor) | `apps/web/src/features/commercial-planner/ColumnSelectorModal.tsx` |

---

## 1. Executive comparison

| Capability | Customers | Products | Distributors (master tab) |
|------------|-----------|----------|---------------------------|
| URL-driven list filters + sort + paging | Yes (richest) | Yes (lifecycle/date-heavy) | Yes (linkage/alias-focused) |
| Saved views (localStorage query snapshots) | No | Yes | No |
| Grouped column picker dialog | Yes (bespoke) | Yes (bespoke + dynamic specs) | Yes (bespoke) |
| Uses `ColumnSelectorModal` | **No** | **No** | **No** |
| AG Grid column state persistence | Yes | Yes | Yes |
| Inline cell edit → `apiPatch` | Yes (many fields) | Yes (many fields) | Yes (`distributor_name` only on master) |
| Detail drawer | Yes (locations/contacts/terms + promote) | Yes (summary + economics + active toggle) | Yes (locations/contacts/terms + promote) |
| `BulkSelectionToolbar` (normal ↔ selecting) | Yes | Yes | Yes |
| Bulk delete preview/confirm | Yes | Yes | Yes |
| Row-level promote | Yes | No | Yes |
| Bulk promote dialog | Yes | No | No (U-B2) |
| Park / Exclude disposition | Yes | No | No (U-B2 / 0071 column) |
| Extra page chrome | Create + CSV paste + duplicates links | CSV paste + DSI conflict clear | Tabs: master + transitional sell-out/inbound grids |

**Canonical extraction target for U-G2:** Customers is the richest shared surface (URL filters, bulk selection, promote, disposition, column picker, drawer slot). Products/distributors adopt the shell later (U-B2).

---

## 2. Capability matrix (detail)

Legend: **Y** = present · **N** = absent · **P** = partial / page-specific · **—** = N/A

### 2.1 Search / URL filters

| Concern | Customers | Products | Distributors |
|---------|-----------|----------|--------------|
| `useSearchParams` + `setParamState` | Y | Y | Y |
| Default empty URL → seed `page` / `page_size` / `sort_*` | Y | Y | N (reads defaults inline; no empty-URL seed effect) |
| `q` text search | Y | Y | Y |
| `page`, `page_size` | Y (default 50) | Y (default 50) | Y (default 25) |
| `sort_by`, `sort_dir` | Y (`customer_code` / asc; API maps code/name) | Y (`sku` / asc) | Y (`distributor_code` / asc) |
| Entity-specific filters | `customer_status`, `disposition`, `partner_tier`, `region_code`, `channel_code`, `preferred_distributor_code`, `min_alias_count`, `alias_link` | `is_active`, `category`, `lifecycle_status`, `launch_date_from/to`, `retired_date_from/to` | `linkage_status`, `min_alias_count`, `alias_link` |
| `create=1` opens create dialog | Y | N | N (local `addOpen` state) |
| Clear-filters control | Y | Y | P (filters clearable individually; no single clear-all) |
| Saved views of query string | N | Y (`cip.admin.products.savedViews.v1`) | N |

**Shell implication:** Shell owns generic URL helpers (`page` / `page_size` / `q` / `sort_by` / `sort_dir` + `setParamState`). Entity filter fields stay page-owned via a `filterSlot` / `extraFilterParams` render prop.

### 2.2 Column picker

| Concern | Customers | Products | Distributors |
|---------|-----------|----------|--------------|
| “Columns” toolbar button | Y | Y | Y |
| Dialog with search + grouped `Checkbox` / `FormControlLabel` | Y | Y | Y |
| Static column groups | Y (`STATIC_CUSTOMER_COLUMN_GROUPS`) | Y (`STATIC_PRODUCT_COLUMN_GROUPS`) | Y (`STATIC_DISTRIBUTOR_MASTER_COLUMN_GROUPS`) |
| Dynamic columns | N | Y (flattened `specs_*` keys accumulated across pages) | N |
| Default initially hidden fields applied in `onGridReady` | Y | Y | Y |
| “Reset column layout” (remove localStorage + reload) | Y | Y | Y |
| `ColumnSelectorModal` (commercial planner) | **N — must not be imported or regress** | same | same |

**Non-regression anchor — `ColumnSelectorModal`:**

- Lives only under commercial planner (`apps/web/src/features/commercial-planner/ColumnSelectorModal.tsx`).
- Props: `open`, `onClose`, `lines`, `optionalVisible`, `onChange`, `onReset`, `onPreset`, optional `columnMeta` / `specKeyVisible` / `onSpecKeyToggle`.
- Presets + coverage chips are planner-specific.
- **U-G2 must not refactor, move, or share-mutate this modal.** Admin master column pickers are a separate pattern (grouped checkboxes over AG Grid `setColumnsVisible`). If a shared picker is extracted later, it must be a new component — not a fork of `ColumnSelectorModal`.

### 2.3 Inline edit

| Concern | Customers | Products | Distributors master |
|---------|-----------|----------|---------------------|
| `singleClickEdit: true` | Y | Y | Y |
| Editable fields | name, status, partner_tier, region/channel/preferred dist codes, account_owner, notes | name, category, form_factor, lifecycle, launch/retired dates, is_active | `distributor_name` only |
| Identity / code columns editable | N (`customer_code` locked) | N (`sku` locked) | N (`distributor_code` locked) |
| Select cell editors | Y (status, tier, region/channel/dist codes) | P (boolean `is_active`; free text otherwise) | N |
| Patch on `onCellValueChanged` | `PATCH /api/v1/customers/{id}` | `PATCH /api/v1/products/{id}` | `PATCH /api/v1/distributors/{id}` |
| Status patch warnings | Y (`warnings` from API) | N | N |

**Shell implication:** Shell accepts `columnDefs` + optional `onCellValueChanged` / `gridOptions` merge; does **not** own field→API mapping.

### 2.4 Bulk selection semantics

Shared component: `BulkSelectionToolbar` (`BulkTableSelectionMode = 'normal' | 'selecting'`).

| Concern | All three master grids |
|---------|------------------------|
| Enter via “Bulk actions” | Y |
| Exit via “Cancel” → mode `normal` | Y |
| Selecting mode enables AG Grid `rowSelection: { mode: 'multiRow', checkboxes: true, headerCheckbox: true, enableClickSelection: false }` | Y |
| Grid remount key when mode flips (`EnterpriseDataGrid` also keys on pathname + rowSelection) | Y (pages pass explicit `key={…-bulk|…-normal}`) |
| “Select visible” = `forEachNodeAfterFilterAndSort` → `setSelected(true)` | Y |
| “Deselect all” = `deselectAll()` | Y |
| Selected count chip + visible row count | Y |
| Danger action = preview bulk delete (not immediate delete) | Y → `MasterBulkDeleteImpactDialog` |
| Preview endpoints | `/customers|products|distributors/bulk-delete-preview` |
| Confirm endpoints | `/customers|products|distributors/bulk-delete-confirm` |
| Selection clears after successful bulk delete | Y |

**Non-regression anchor — steward / selection checkboxes:**

- Master bulk checkboxes appear **only** in `selecting` mode (not always-on).
- `enableClickSelection: false` — row click must not toggle selection (preserves Open / Promote / inline edit UX).
- Header checkbox + “Select visible” operate on **filtered/sorted displayed** rows, not the full server result set.
- Steward import workspaces (DSI / shipment candidate checkboxes) are a **different** surface; shell extraction must not change steward checkbox behaviour or shared AG Grid defaults in a way that bleeds into import steward panels.
- Do not conflate master bulk checkboxes with commercial-planner column checkboxes inside `ColumnSelectorModal`.

### 2.5 Drawers

| Concern | Customers | Products | Distributors |
|---------|-----------|----------|--------------|
| Right `Drawer` on row “Open” | Y | Y | Y |
| Summary fields | Y | Y | Y |
| Nested CRUD (locations/contacts) | Y | N | Y |
| Domain panel | `CustomerCommercialTermsPanel` | `ProductSkuEconomicsPanel` | `DistributorCommercialTermsPanel` |
| Promote CTA in drawer | Y (`pmg-promote-drawer`) | N | Y (when provisional) |
| Active toggle in drawer | N | Y | N |
| Offset under app chrome (`top` / height calc) | Y | Y | P (simpler drawer; still right-anchored) |

**Shell implication:** `drawerSlot` / `renderDrawer(row)` — shell opens/closes; page owns content.

### 2.6 Toolbar actions (promote / disposition / delete / other)

| Action | Customers | Products | Distributors |
|--------|-----------|----------|--------------|
| Add / create | Y (button + `?create=1`) | N (CSV / imports) | Y (dialog) |
| Import deep-link | Y (`customer_master`) | via empty-state / getting-started | Y when template ready |
| Duplicates links | Y (alias-scope + name-similarity) | N | Y (name-similarity) |
| Row Promote | Y (`pmg-promote-row`) | N | Y (in Details col / drawer) |
| Bulk promote… | Y (`CustomerBulkPromoteDialog`) | N | N (planned U-B2) |
| Park / Exclude… | Y (`CustomerDispositionDialog`; requires selecting mode + selection) | N | N (planned U-B2) |
| Disposition URL filter | Y (`disposition`) | N | N |
| Disposition column (read-only chips) | Y (`no_code_disposition`) | N | N (column exists in DB after 0071; UI later) |
| Quick paste CSV | Y (legacy) | Y | N on master (import route) |
| Columns / Reset layout | Y | Y | Y |
| `ModuleGridToolbar` refresh | Y | Y | Y |
| Row delete (`gridDeleteColumn`) | Y | Y (+ DSI conflict recovery UI) | Y |
| Bulk delete via toolbar danger | Y | Y | Y |
| Extra grids on same page | N | N | Y (sell-out + inbound transitional tabs; own inline edit/delete; **out of shell v1**) |

### 2.7 localStorage keys

| Key | Owner | Payload |
|-----|-------|---------|
| `cip.admin.customers.gridState.v1` | Customers | AG Grid column state (order/hide/pin/width) |
| `cip.admin.products.gridState.v1` | Products | AG Grid column state |
| `cip.admin.products.savedViews.v1` | Products | Named URL query snapshots (`SavedView[]`) |
| `cip.admin.distributors.master.gridState.v1` | Distributors master | AG Grid column state |

**Conventions:** `cip.` prefix, versioned suffix (`.v1`), admin master grids use `cip.admin.<entity>.gridState.v1` (distributors inserts `.master.` because the page hosts multiple grids).

**Shell implication:** `gridStateStorageKey: string` required; optional `savedViewsStorageKey` for products-only behaviour (or keep saved views page-owned).

### 2.8 Shared building blocks already in use

| Building block | Role | Shell should… |
|----------------|------|----------------|
| `EnterpriseDataGrid` | Thin AG Grid + MUI theme vars | Wrap, not replace |
| `BulkSelectionToolbar` | Mode toggle + select visible + preview danger | Compose as optional region |
| `MasterBulkDeleteImpactDialog` | Preview/confirm bulk delete | Stay page-wired (or optional slot) |
| `gridDeleteColumn` | Per-row delete confirm | Stay in page `columnDefs` |
| `ModuleDataSection` / `ModuleGridToolbar` / `PageHeader` | Loading/empty/refresh chrome | Compose around shell or leave page-owned |
| Promote / disposition dialogs | Entity-specific | Page slots only |

---

## 3. What is shared vs page-owned (extraction boundary)

### Shared → `MasterDataGridShell` (U-G2)

1. URL param helpers for paging/sort/q (and optional reset-to-defaults).
2. Column state persist/restore/reset against a storage key + default-hidden field list.
3. Grouped column-picker dialog shell (search + checkbox groups + Done); groups/labels injected.
4. Bulk selection mode wiring into `EnterpriseDataGrid` (`rowSelection`, remount key, select-visible/deselect, visible count).
5. Layout slots: leading toolbar actions, filter row, trailing toolbar, grid, pagination footer, drawer host.
6. Consistent grid height / `ModuleDataSection` wiring **if** all three already agree (they mostly do).

### Page-owned (do not swallow in shell v1)

1. Column field lists, editable maps, `onCellValueChanged` patch logic.
2. Entity filters beyond q/sort/page.
3. Promote / bulk promote / disposition dialogs and visibility rules.
4. Drawer body (locations, contacts, commercial terms, economics).
5. Create/CSV paste/DSI conflict/duplicates navigation.
6. Products saved views + dynamic spec columns.
7. Distributors transitional sell-out/inbound tabs and fact-mapping grids.
8. API query keys and list fetch shapes.

---

## 4. Proposed `MasterDataGridShell` prop contract

TypeScript-ish sketch for U-G2 (customers first). Names are proposals — adjust during implement if existing helpers already cover pieces.

```ts
import type { ColDef, GridApi, GridOptions, CellValueChangedEvent } from 'ag-grid-community';
import type { ReactNode } from 'react';
import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

/** Column group for the admin-style picker (not ColumnSelectorModal). */
export type MasterColumnPickerGroup = {
  label: string;
  /** AG Grid colIds / field names */
  fields: string[];
};

export type MasterGridUrlState = {
  page: number;
  pageSize: number;
  q: string;
  sortBy: string;
  sortDir: 'asc' | 'desc';
};

export type MasterDataGridShellProps<TRow extends { id: number }> = {
  /** Stable id for testids / remount keys, e.g. "customers" | "products" | "distributors" */
  entityKey: string;

  // ── Data ──────────────────────────────────────────────
  rows: TRow[];
  columnDefs: ColDef<TRow>[];
  total: number;
  isLoading?: boolean;
  isError?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  empty?: {
    title: string;
    description?: ReactNode;
    primary?: { label: string; href: string };
    secondary?: { label: string; href: string };
  };
  intro?: ReactNode;

  // ── URL list state (shell-owned subset) ───────────────
  url: MasterGridUrlState;
  /** Patch URL params; `resetPage` mirrors current setParamState second arg */
  onUrlChange: (patch: Record<string, string | null>, resetPage?: boolean) => void;
  defaultPageSize: number;
  defaultSortBy: string;
  defaultSortDir: 'asc' | 'desc';
  pageSizeOptions?: number[]; // default [25, 50, 100, 200]

  // ── Column layout persistence ─────────────────────────
  gridStateStorageKey: string;
  defaultInitiallyHiddenFields?: readonly string[];
  columnPickerTitle: string;
  columnPickerGroups: MasterColumnPickerGroup[];
  /** Optional extra groups (e.g. products discovered specs) */
  columnPickerExtraGroups?: MasterColumnPickerGroup[];
  columnLabelByField?: Record<string, string>;

  // ── Grid behaviour ────────────────────────────────────
  gridHeight?: number | string; // default ~520
  /** Merged into base options; shell adds selection + column-state handlers */
  gridOptions?: GridOptions<TRow>;
  onCellValueChanged?: (e: CellValueChangedEvent<TRow>) => void | Promise<void>;
  /** Expose api to page for select-all / sync visibility / custom actions */
  onGridApiChange?: (api: GridApi<TRow> | null) => void;

  // ── Bulk selection ────────────────────────────────────
  bulkSelectionEnabled?: boolean; // default true
  bulkSelectionMode: BulkTableSelectionMode;
  onBulkSelectionModeChange: (mode: BulkTableSelectionMode) => void;
  /** Called when user clicks Preview delete (page opens MasterBulkDeleteImpactDialog) */
  onPreviewBulkDelete: () => void;
  previewBulkDeleteDisabled?: boolean;
  bulkBusy?: boolean;
  /** Optional actions shown only while selecting (e.g. Park/Exclude) */
  bulkSelectingActions?: ReactNode;

  // ── Slots (page-owned chrome) ─────────────────────────
  /** Buttons above filters: Add, Import, Bulk promote, CSV, … */
  toolbarStart?: ReactNode;
  /** Extra filter controls between q/sort and entity-specific fields */
  filterSlot?: ReactNode;
  /** After Columns / Reset / BulkSelectionToolbar */
  toolbarEnd?: ReactNode;
  /** Right drawer body when a row is selected; shell may own open state or accept controlled */
  drawer?: {
    open: boolean;
    onClose: () => void;
    width?: number;
    title?: string;
    children: ReactNode;
  };

  // ── Optional products-only (keep out of v1 if unused) ─
  savedViews?: {
    storageKey: string;
    views: { name: string; query: string }[];
    onChange: (views: { name: string; query: string }[]) => void;
  };
};
```

### Controlled vs uncontrolled notes

- **Bulk mode:** controlled (`bulkSelectionMode` + `onBulkSelectionModeChange`) — pages already own this state and gate disposition/promote.
- **Drawer:** controlled object — pages already use `selectedRow` / `drawerRow`.
- **Column picker open state:** can be internal to the shell.
- **GridApi:** shell holds ref; notifies via `onGridApiChange` so pages can `forEachNodeAfterFilterAndSort` if they keep custom bulk actions outside the toolbar.

### Explicit non-goals for shell v1

- Do not import or wrap `ColumnSelectorModal`.
- Do not implement promote/disposition/mint APIs.
- Do not absorb distributors transitional tabs.
- Do not change `EnterpriseDataGrid` public props beyond what composition needs.
- Do not alter steward import checkbox semantics.

---

## 5. U-G2 acceptance anchors (from this matrix)

When implementing the shell + customers parity:

1. **URL:** Existing customer query params continue to round-trip (`q`, status, disposition, tier, region, channel, preferred dist, alias filters, sort, page).
2. **Columns:** `cip.admin.customers.gridState.v1` read/write/reset behaviour unchanged; grouped checkbox picker still works.
3. **Bulk:** `BulkSelectionToolbar` + selecting-mode checkboxes + select visible + bulk-delete preview unchanged (`data-testid`s: `bulk-selection-toolbar`, `bulk-preview-danger`, etc.).
4. **Promote / disposition:** `pmg-promote-row`, `pmg-promote-drawer`, `bulk-promote-open`, `disposition-open`, `disposition-filter` remain functional.
5. **Non-regression:** Commercial planner `ColumnSelectorModal` and import steward checkboxes untouched (no shared default that forces always-on row checkboxes).

---

## 6. Recommended rollout

| Unit | Work |
|------|------|
| **U-G1** (this doc) | Matrix + prop contract — review gate |
| **U-G2** | Implement `MasterDataGridShell`; refactor **customers** only to parity |
| **U-B2** | Adopt shell on products + distributors; distributor bulk promote + disposition UI |

---

## 7. Open questions for review (non-blocking)

1. Should products **saved views** stay fully page-owned in U-B2, or become an optional shell region?
2. Should the column picker become a named shared component (`MasterColumnPickerDialog`) separate from the shell layout wrapper?
3. Distributors default `page_size` is 25 vs 50 on customers/products — normalize in shell defaults or preserve per-entity `defaultPageSize`? (**Recommend:** preserve per-entity.)
)

/**
 * Single source of truth for AG Grid row and header heights per density.
 *
 * Consumers:
 *   - `components/EnterpriseDataGrid.tsx` — the `rowHeight` / `headerHeight` props AND the inline
 *     `--ag-row-height` / `--ag-header-height` CSS variables, so the grid can never disagree with itself.
 *   - `features/plan-vs-executed/gridPagination.ts` — re-exports the legacy `STANDARD_*` / `COMPACT_*`
 *     names and `gridRowMetrics` so existing imports keep working; `paginatedGridHeight()` sizes
 *     paginated shells from the same numbers.
 *   - Any caller that spreads `gridRowMetrics(...)` into `gridOptions` (e.g. the shipping page).
 *
 * `packages/ui/src/agGridMuiTheme.ts` still emits these two variables with its own literals.
 * `EnterpriseDataGrid` overrides them inline from here; once `packages/ui` is inside the accepted
 * `change_paths`, hoist this file into `@cip/ui` and delete that emission (N-0031 acceptance criteria).
 *
 * The values here are the CURRENT product values: comfortable 42/42, compact 34/36. The density
 * proposal (40/40 rows, 13px type) is a separate node — do not change numbers in this file for it
 * without that node's evidence.
 */

export type GridDensity = 'comfortable' | 'compact';

export type GridRowMetrics = Readonly<{ rowHeight: number; headerHeight: number }>;

export const GRID_DENSITY: Readonly<Record<GridDensity, GridRowMetrics>> = {
  comfortable: { rowHeight: 42, headerHeight: 42 },
  compact: { rowHeight: 34, headerHeight: 36 },
};

/** Anything that is not exactly `'compact'` is comfortable — the theme's own fallback rule. */
export function normalizeGridDensity(value: unknown): GridDensity {
  return value === 'compact' ? 'compact' : 'comfortable';
}

/** Row and header heights for a density. Safe to spread into AG Grid `gridOptions`. */
export function gridRowMetrics(density: GridDensity | string | undefined = 'comfortable'): GridRowMetrics {
  return GRID_DENSITY[normalizeGridDensity(density)];
}

/** The same numbers as CSS custom properties, for the grid shell's inline style. */
export function gridDensityCssVars(
  density: GridDensity | string | undefined,
): Record<'--ag-row-height' | '--ag-header-height', string> {
  const m = gridRowMetrics(density);
  return { '--ag-row-height': `${m.rowHeight}px`, '--ag-header-height': `${m.headerHeight}px` };
}

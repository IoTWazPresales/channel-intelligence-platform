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
 * `EnterpriseDataGrid` overrides them inline from here. `packages/ui` joined the accepted
 * `change_paths` (Warren, 2026-09-21); hoisting this file into `@cip/ui` and deleting that
 * duplicate emission (N-0031 acceptance criteria) remains open and out of scope for Stage 2.2/2.3.
 *
 * Comfortable is **40/40** (Stage 2.3, `docs/design/STAGED_WORK_PLAN.md`; D2) — not the lab's
 * original 36/36 proposal in `DENSITY_PROPOSAL_OPERATOR_DATA_SCALE.md` / `DensitySurface.tsx`,
 * which stays frozen as the historical audit record. Compact is unchanged at 34/36. The grid-scoped
 * 13px type size is a separate constant, `AG_GRID_FONT_SIZE` in `packages/ui/src/agGridMuiTheme.ts`.
 */

export type GridDensity = 'comfortable' | 'compact';

export type GridRowMetrics = Readonly<{ rowHeight: number; headerHeight: number }>;

export const GRID_DENSITY: Readonly<Record<GridDensity, GridRowMetrics>> = {
  comfortable: { rowHeight: 40, headerHeight: 40 },
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

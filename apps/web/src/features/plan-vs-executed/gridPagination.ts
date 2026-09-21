import { GRID_DENSITY, gridRowMetrics, type GridDensity } from '@/theme/gridDensity';

/** Fixed-height AG Grid shell for paginated grids (no autoHeight / row-count hacks). */
export const PAGINATED_GRID_PAGE_SIZE = 15;
export const DRILL_GRID_PAGE_SIZE = 20;
const PAGINATION_BAR_HEIGHT = 48;

/**
 * Row/header heights are re-exported from the single source (`@/theme/gridDensity`) so existing
 * imports keep working. They are the same objects `EnterpriseDataGrid` renders with, so the
 * paginated shell height below can no longer drift from the rows inside it.
 */
export const STANDARD_ROW_HEIGHT = GRID_DENSITY.comfortable.rowHeight;
export const COMPACT_ROW_HEIGHT = GRID_DENSITY.compact.rowHeight;
export const STANDARD_HEADER_HEIGHT = GRID_DENSITY.comfortable.headerHeight;
export const COMPACT_HEADER_HEIGHT = GRID_DENSITY.compact.headerHeight;

export { gridRowMetrics };
export type { GridDensity };

export function paginatedGridHeight(
  pageSize: number,
  opts?: { headerHeight?: number; rowHeight?: number },
): number {
  const headerHeight = opts?.headerHeight ?? STANDARD_HEADER_HEIGHT;
  const rowHeight = opts?.rowHeight ?? STANDARD_ROW_HEIGHT;
  return headerHeight + rowHeight * pageSize + PAGINATION_BAR_HEIGHT;
}

export const VALUE_UNAVAILABLE_TOOLTIP =
  'Value unavailable — plan pricing or FX bridge missing for this exposure';

export const ENTITY_LENS_HEADERS = {
  customer: 'Customer',
  product: 'Product',
  bu: 'BU',
} as const;

export type ExceptionLens = keyof typeof ENTITY_LENS_HEADERS;

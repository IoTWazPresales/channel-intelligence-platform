/** Fixed-height AG Grid shell for paginated grids (no autoHeight / row-count hacks). */
export const PAGINATED_GRID_PAGE_SIZE = 15;
export const DRILL_GRID_PAGE_SIZE = 20;
const PAGINATION_BAR_HEIGHT = 48;

/** Standard single-line row height — must match EnterpriseDataGrid default (42) and gridOptions.rowHeight. */
export const STANDARD_ROW_HEIGHT = 42;
export const COMPACT_ROW_HEIGHT = 34;
export const STANDARD_HEADER_HEIGHT = 42;
export const COMPACT_HEADER_HEIGHT = 36;

export function gridRowMetrics(density: 'comfortable' | 'compact' = 'comfortable') {
  const compact = density === 'compact';
  return {
    rowHeight: compact ? COMPACT_ROW_HEIGHT : STANDARD_ROW_HEIGHT,
    headerHeight: compact ? COMPACT_HEADER_HEIGHT : STANDARD_HEADER_HEIGHT,
  };
}

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

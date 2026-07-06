/** Fixed-height AG Grid shell for paginated grids (no autoHeight / row-count hacks). */
export const PAGINATED_GRID_PAGE_SIZE = 15;
export const DRILL_GRID_PAGE_SIZE = 20;
const PAGINATION_BAR_HEIGHT = 52;

export function paginatedGridHeight(
  pageSize: number,
  opts?: { headerHeight?: number; rowHeight?: number },
): number {
  const headerHeight = opts?.headerHeight ?? 42;
  const rowHeight = opts?.rowHeight ?? 42;
  return headerHeight + rowHeight * pageSize + PAGINATION_BAR_HEIGHT;
}

export const VALUE_UNAVAILABLE_TOOLTIP =
  'Value unavailable — plan pricing or FX bridge missing for this exposure';

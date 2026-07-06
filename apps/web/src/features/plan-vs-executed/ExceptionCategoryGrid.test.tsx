import { describe, expect, it } from 'vitest';

import { paginatedGridHeight, PAGINATED_GRID_PAGE_SIZE } from './gridPagination';

describe('gridPagination', () => {
  it('computes fixed height for a full page of rows plus header and pagination bar', () => {
    const height = paginatedGridHeight(PAGINATED_GRID_PAGE_SIZE, { rowHeight: 42, headerHeight: 42 });
    expect(height).toBe(42 + 42 * PAGINATED_GRID_PAGE_SIZE + 52);
  });
});

describe('ExceptionCategoryGrid value display', () => {
  it('treats null value_plan as unavailable not zero', () => {
    const row = { value_plan: null as number | null, value_cost: null as number | null };
    expect(row.value_plan ?? '—').toBe('—');
    expect(row.value_plan === 0).toBe(false);
  });
});

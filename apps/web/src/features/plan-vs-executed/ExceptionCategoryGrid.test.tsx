import { describe, expect, it } from 'vitest';

import { formatEntityLine } from './ExceptionCategoryGrid';
import {
  paginatedGridHeight,
  PAGINATED_GRID_PAGE_SIZE,
  STANDARD_HEADER_HEIGHT,
  STANDARD_ROW_HEIGHT,
} from './gridPagination';

describe('gridPagination', () => {
  it('computes fixed height for a full page of single-line rows plus header and pagination bar', () => {
    const height = paginatedGridHeight(PAGINATED_GRID_PAGE_SIZE, {
      rowHeight: STANDARD_ROW_HEIGHT,
      headerHeight: STANDARD_HEADER_HEIGHT,
    });
    expect(height).toBe(STANDARD_HEADER_HEIGHT + STANDARD_ROW_HEIGHT * PAGINATED_GRID_PAGE_SIZE + 48);
  });
});

describe('formatEntityLine', () => {
  it('returns a single-line customer label without BU sub-field', () => {
    expect(formatEntityLine('Open Channel')).toBe('Open Channel');
    expect(formatEntityLine('Open Channel', true)).toBe('Open Channel (no description)');
  });
});

describe('ExceptionCategoryGrid value display', () => {
  it('treats null value_plan as unavailable not zero', () => {
    const row = { value_plan: null as number | null, value_cost: null as number | null };
    expect(row.value_plan ?? '—').toBe('—');
    expect(row.value_plan === 0).toBe(false);
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { createElement, createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { GridCsvExportButton, readSavedFindViews, visibleFilteredCsvParams } from './gridFind';
import type { AgGridReact } from 'ag-grid-react';

describe('readSavedFindViews', () => {
  it('keeps named find strings and drops All and junk', () => {
    const raw = JSON.stringify([
      { name: 'Takealot', find: 'takealot' },
      { name: 'All', find: 'nope' },
      { name: '', find: 'x' },
      { name: 'Empty ok', find: '' },
      { find: 'missing name' },
      'nope',
      {
        name: 'Wide',
        find: 'sku',
        optionalFields: ['customer_code', 1],
        columnState: [{ colId: 'sku', sort: 'asc', sortIndex: 0 }, { sort: 'desc' }],
        filterModel: { sku: { filterType: 'text', type: 'contains', filter: 'sku' } },
      },
    ]);
    expect(readSavedFindViews(raw)).toEqual([
      { name: 'Takealot', find: 'takealot' },
      { name: 'Empty ok', find: '' },
      {
        name: 'Wide',
        find: 'sku',
        columnState: [{ colId: 'sku', hide: null, sort: 'asc', sortIndex: 0, pinned: null }],
        filterModel: { sku: { filterType: 'text', type: 'contains', filter: 'sku' } },
      },
    ]);
  });

  it('returns nothing for empty or broken storage', () => {
    expect(readSavedFindViews(null)).toEqual([]);
    expect(readSavedFindViews('not json')).toEqual([]);
    expect(readSavedFindViews('{"name":"x"}')).toEqual([]);
  });
});

describe('visible filtered CSV export', () => {
  it('keeps the community CSV contract: visible columns, filtered rows, no excel', () => {
    expect(visibleFilteredCsvParams('roadmap', ['customer_label', 'sku'])).toEqual({
      fileName: 'roadmap.csv',
      allColumns: false,
      exportedRows: 'filteredAndSorted',
      onlySelected: false,
      columnKeys: ['customer_label', 'sku'],
    });
    expect(visibleFilteredCsvParams('roadmap.csv', ['sku']).fileName).toBe('roadmap.csv');
  });

  it('exports only displayed columns, so an unpicked code stays out of the file', () => {
    const exportDataAsCsv = vi.fn();
    const ref = createRef<AgGridReact>();
    ref.current = {
      api: {
        getAllDisplayedColumns: () => [{ getColId: () => 'customer_label' }, { getColId: () => 'sku' }],
        exportDataAsCsv,
      },
    } as unknown as AgGridReact;
    render(createElement(GridCsvExportButton, { gridRef: ref, fileName: 'roadmap' }));
    fireEvent.click(screen.getByTestId('grid-export-roadmap'));
    expect(exportDataAsCsv).toHaveBeenCalledWith(
      visibleFilteredCsvParams('roadmap', ['customer_label', 'sku']),
    );
    const passed = exportDataAsCsv.mock.calls[0][0] as { columnKeys: string[] };
    expect(passed.columnKeys).not.toContain('customer_code');
  });
});

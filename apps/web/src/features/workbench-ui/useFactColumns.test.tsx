import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FactColumnPicker } from './FactColumnPicker';
import { gridLayoutStorageKey, useFactColumns, type GridFieldItem } from './useFactColumns';

const ITEMS: GridFieldItem[] = [
  { field: 'retire_target', label: 'Retire Target', group: 'fact', default_hidden: true },
  { field: 'product_id', label: 'Product Id', group: 'fact', default_hidden: true },
  { field: 'customer_code', label: 'Customer code', group: 'reference', default_hidden: true },
];

const IDENTITY_ITEMS: GridFieldItem[] = [
  { field: 'sku', label: 'SKU', group: 'identity', default_hidden: true },
  { field: 'sales_model_name', label: 'Sales model', group: 'identity', default_hidden: true },
];

const PROFILE_URL = '/api/v1/auth/tenant-commercial-profile';
let tenantPreference: 'sku' | 'sales_model' | 'both' = 'sku';
let registryItems: GridFieldItem[] = ITEMS;

const apiGetMock = vi.fn(async (url: string) => {
  if (url === PROFILE_URL) return { line_identifier_preference: tenantPreference };
  return { grid_id: 'roadmap', items: registryItems };
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useFactColumns', () => {
  beforeEach(() => {
    localStorage.clear();
    apiGetMock.mockClear();
    tenantPreference = 'sku';
    registryItems = ITEMS;
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches the registry for its grid and starts with no optional columns (codes hidden)', async () => {
    const { result } = renderHook(() => useFactColumns('roadmap'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pickerProps.items).toHaveLength(3));
    expect(apiGetMock).toHaveBeenCalledWith('/api/v1/grid-fields/roadmap');
    expect(result.current.optionalColDefs).toEqual([]);
    expect(result.current.pickerProps.selected).toEqual([]);
  });

  it('toggling a field adds a labelled ColDef and persists; reset restores the default', async () => {
    const { result } = renderHook(() => useFactColumns('roadmap'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pickerProps.gridReady).toBe(true));
    act(() => result.current.pickerProps.onToggle('customer_code', true));
    expect(result.current.optionalColDefs.map((c) => [c.field, c.headerName])).toEqual([
      ['customer_code', 'Customer code'],
    ]);
    expect(JSON.parse(localStorage.getItem(gridLayoutStorageKey('roadmap')) ?? '{}')).toEqual({
      optionalFields: ['customer_code'],
    });
    act(() => result.current.pickerProps.onReset());
    expect(result.current.optionalColDefs).toEqual([]);
    expect(JSON.parse(localStorage.getItem('cip.grid.roadmap.optional.v1') ?? '{}').optionalFields).toEqual([]);
  });

  it('restores a saved layout and prunes fields the registry no longer offers', async () => {
    localStorage.setItem(
      gridLayoutStorageKey('roadmap'),
      JSON.stringify({ optionalFields: ['retire_target', 'gone_column'] })
    );
    const { result } = renderHook(() => useFactColumns('roadmap'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pickerProps.selected).toEqual(['retire_target']));
    expect(result.current.optionalColDefs.map((c) => c.field)).toEqual(['retire_target']);
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(gridLayoutStorageKey('roadmap')) ?? '{}').optionalFields).toEqual([
        'retire_target',
      ])
    );
  });

  it('keeps other keys in an existing storage object (inbound pageSize) via storageKey override', async () => {
    const key = 'cip.commercial.inbound-shipments.grid.optional.v1';
    localStorage.setItem(key, JSON.stringify({ optionalFields: ['product_id'], pageSize: 100 }));
    const { result } = renderHook(() => useFactColumns('inbound-shipments', { storageKey: key }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.optionalFields).toEqual(['product_id']));
    act(() => result.current.pickerProps.onToggle('retire_target', true));
    expect(JSON.parse(localStorage.getItem(key) ?? '{}')).toEqual({
      optionalFields: ['product_id', 'retire_target'],
      pageSize: 100,
    });
    expect(localStorage.getItem(gridLayoutStorageKey('inbound-shipments'))).toBeNull();
  });

  it('survives a localStorage failure (layout just does not persist)', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const { result } = renderHook(() => useFactColumns('roadmap'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pickerProps.gridReady).toBe(true));
    act(() => result.current.pickerProps.onToggle('product_id', true));
    expect(result.current.optionalColDefs.map((c) => c.field)).toEqual(['product_id']);
  });

  it('applies per-field formatters and colDef extras', async () => {
    const { result } = renderHook(
      () =>
        useFactColumns('roadmap', {
          formatters: { product_id: (v) => `#${String(v)}` },
          colDefFor: (f) => (f === 'product_id' ? { minWidth: 99 } : {}),
        }),
      { wrapper: wrapper() }
    );
    await waitFor(() => expect(result.current.pickerProps.gridReady).toBe(true));
    act(() => result.current.pickerProps.onToggle('product_id', true));
    const col = result.current.optionalColDefs[0];
    expect(col.minWidth).toBe(99);
    const fmt = col.valueFormatter as (p: { value: unknown }) => string;
    expect(fmt({ value: 7 })).toBe('#7');
  });

  describe('line identity (N-0053)', () => {
    const LINE = { sku: 'sku', salesModel: 'sales_model_name' } as const;

    it('returns no identity columns and the raw registry when no lineIdentifier is given', async () => {
      registryItems = [...IDENTITY_ITEMS, ...ITEMS];
      const { result } = renderHook(() => useFactColumns('roadmap'), { wrapper: wrapper() });
      await waitFor(() => expect(result.current.pickerProps.items).toHaveLength(5));
      expect(result.current.identityColDefs).toEqual([]);
    });

    it('sku preference pins one welded column and offers only Sales model in the picker', async () => {
      registryItems = [...IDENTITY_ITEMS, ...ITEMS];
      const { result } = renderHook(
        () => useFactColumns('roadmap', { lineIdentifier: LINE, lineIdentifierColDef: { pinned: 'left' } }),
        { wrapper: wrapper() }
      );
      await waitFor(() => expect(result.current.pickerProps.items).toHaveLength(4));
      expect(result.current.pickerProps.items.map((i) => i.field)).toEqual([
        'sales_model_name',
        'retire_target',
        'product_id',
        'customer_code',
      ]);
      await waitFor(() => expect(result.current.identityColDefs).toHaveLength(1));
      expect(result.current.identityColDefs[0]).toMatchObject({
        colId: 'line_identifier',
        headerName: 'SKU',
        pinned: 'left',
      });
      act(() => result.current.pickerProps.onToggle('sales_model_name', true));
      expect(result.current.optionalColDefs.map((c) => [c.field, c.headerName])).toEqual([
        ['sales_model_name', 'Sales model'],
      ]);
    });

    it('`both` pins two field columns and removes both identifiers from the picker and optional set', async () => {
      tenantPreference = 'both';
      registryItems = [...IDENTITY_ITEMS, ...ITEMS];
      // A Sales model pick saved while the tenant was on `sku` must not become a duplicate column.
      localStorage.setItem(gridLayoutStorageKey('roadmap'), JSON.stringify({ optionalFields: ['sales_model_name'] }));
      const { result } = renderHook(
        () => useFactColumns('roadmap', { lineIdentifier: LINE, lineIdentifierColDef: { minWidth: 110 } }),
        { wrapper: wrapper() }
      );
      await waitFor(() => expect(result.current.identityColDefs).toHaveLength(2));
      expect(result.current.identityColDefs.map((c) => [c.colId, c.field, c.headerName, c.minWidth])).toEqual([
        ['line_identifier_sku', 'sku', 'SKU', 110],
        ['line_identifier_sales_model', 'sales_model_name', 'Sales model', 110],
      ]);
      await waitFor(() => expect(result.current.pickerProps.items).toHaveLength(3));
      expect(result.current.pickerProps.items.every((i) => i.group !== 'identity')).toBe(true);
      expect(result.current.optionalColDefs).toEqual([]);
      // The stored pick survives (pruned against the full registry) so it returns on a flip back.
      expect(JSON.parse(localStorage.getItem(gridLayoutStorageKey('roadmap')) ?? '{}').optionalFields).toEqual([
        'sales_model_name',
      ]);
    });
  });
});

describe('FactColumnPicker', () => {
  it('shows fact fields, then a Reference group, and toggles through the shared dialog', () => {
    const onToggle = vi.fn();
    const onReset = vi.fn();
    render(
      <FactColumnPicker
        open
        onClose={vi.fn()}
        gridId="roadmap"
        items={ITEMS}
        selected={['product_id']}
        onToggle={onToggle}
        onReset={onReset}
        gridReady
        loading={false}
      />
    );
    expect(screen.getByTestId('fact-column-picker-roadmap')).toBeInTheDocument();
    expect(screen.getByText('Fact fields')).toBeInTheDocument();
    expect(screen.getByText('Reference')).toBeInTheDocument();
    const product = screen.getByTestId('master-column-toggle-product_id').querySelector('input')!;
    expect(product).toBeChecked();
    fireEvent.click(screen.getByTestId('master-column-toggle-customer_code').querySelector('input')!);
    expect(onToggle).toHaveBeenCalledWith('customer_code', true);
    fireEvent.click(screen.getByTestId('fact-column-picker-roadmap-reset'));
    expect(onReset).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Search columns'), { target: { value: 'customer' } });
    expect(screen.queryByTestId('master-column-toggle-product_id')).not.toBeInTheDocument();
    expect(screen.getByTestId('master-column-toggle-customer_code')).toBeInTheDocument();
  });

  it('lists a Line identity group first when the registry offers an identifier the preference does not pin', () => {
    render(
      <FactColumnPicker
        open
        onClose={vi.fn()}
        gridId="roadmap"
        items={[IDENTITY_ITEMS[1], ...ITEMS]}
        selected={[]}
        onToggle={vi.fn()}
        onReset={vi.fn()}
        gridReady
        loading={false}
      />
    );
    expect(screen.getByText('Line identity')).toBeInTheDocument();
    expect(screen.getByTestId('master-column-toggle-sales_model_name')).toBeInTheDocument();
    expect(screen.queryByTestId('master-column-toggle-sku')).not.toBeInTheDocument();
  });
});

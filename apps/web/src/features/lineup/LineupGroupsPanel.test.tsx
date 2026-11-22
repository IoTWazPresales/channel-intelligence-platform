import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ColDef, GridOptions } from 'ag-grid-community';
import type { ComponentType, CSSProperties, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LineupGroupsPanel } from './LineupGroupsPanel';
import type { LineupPlanRow } from './lineupTypes';
import type { LineupGroup, LineupSlice } from './lineupViews';

const apiPost = vi.hoisted(() => vi.fn());
const grid = vi.hoisted(() => ({
  rows: [] as TestRow[],
  columns: [] as ColDef<TestRow>[],
  options: {} as GridOptions<TestRow>,
}));

vi.mock('@/lib/api', () => ({
  apiPost: (url: string, body?: unknown) => apiPost(url, body),
  safeDisplayError: (error: unknown) => String(error),
}));

vi.mock('@/features/lineup/LineupPlanGrid', () => ({
  LineupPlanGrid: ({ rows, pendingOnly }: { rows: LineupPlanRow[]; pendingOnly: boolean }) => (
    <div data-testid="detail-line-ids">
      {rows
        .filter((row) => !pendingOnly || ['draft', 'pending_approval', 'submitted'].includes(row.approval_status))
        .map((row) => row.id)
        .join(',')}
    </div>
  ),
}));

type TestRow = {
  key: string;
  group: LineupGroup;
  detailRows?: LineupPlanRow[];
};

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: TestRow[];
    columnDefs: ColDef<TestRow>[];
    gridOptions: GridOptions<TestRow>;
  }) => {
    grid.rows = rowData;
    grid.columns = columnDefs;
    grid.options = gridOptions;
    const Detail = gridOptions.fullWidthCellRenderer as ComponentType<{ data: TestRow }>;
    return (
      <div data-testid="group-grid" role="grid">
        <div data-testid="group-headers" role="row">
          {columnDefs.map((column) => (
            <span key={column.colId} role="columnheader">
              {column.headerName}
            </span>
          ))}
        </div>
        {rowData.map((row) => {
          const fullWidth = gridOptions.isFullWidthRow?.({
            rowNode: { data: row },
          } as Parameters<NonNullable<GridOptions<TestRow>['isFullWidthRow']>>[0]);
          if (fullWidth) return <Detail key={row.key} data={row} />;
          return (
            <div
              key={row.key}
              role="row"
              data-testid={`summary-${row.key}`}
              onClick={(event) => gridOptions.onRowClicked?.({
                data: row,
                event: event.nativeEvent,
              } as unknown as Parameters<NonNullable<GridOptions<TestRow>['onRowClicked']>>[0])}
            >
              {columnDefs.map((column) => {
                const renderCell = column.cellRenderer as
                  ((params: { data: TestRow }) => ReactNode) | undefined;
                const getValue = column.valueGetter as
                  ((params: { data: TestRow }) => unknown) | undefined;
                return (
                  <span
                    key={column.colId}
                    role="gridcell"
                    data-testid={`${row.key}-${column.colId}`}
                    style={
                      typeof column.cellStyle === 'object'
                        ? column.cellStyle as CSSProperties
                        : undefined
                    }
                  >
                    {renderCell ? renderCell({ data: row }) : String(getValue?.({ data: row }) ?? '')}
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  },
}));

const rows: LineupPlanRow[] = [
  {
    id: 1, customer_id: 3, customer_name: 'Customer A', customer_code: 'CODE-A',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 11, sku: 'S1', planned_volume_units: 4, approval_status: 'draft',
  },
  {
    id: 2, customer_id: 3, customer_name: 'Customer A', customer_code: 'CODE-A',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 12, sku: 'S2', planned_volume_units: 6, approval_status: 'approved',
  },
  {
    id: 3, customer_id: 4, customer_name: 'Customer B', customer_code: 'CODE-B',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 11, sku: 'S1', planned_volume_units: 1, approval_status: 'approved',
  },
];

function renderPanel({
  slice = null,
  pendingOnly = false,
  productId = null,
  data = rows,
}: {
  slice?: LineupSlice | null;
  pendingOnly?: boolean;
  productId?: number | null;
  data?: LineupPlanRow[];
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const onOpen = vi.fn();
  renderWithProviders(
    <QueryClientProvider client={client}>
      <LineupGroupsPanel
        rows={data}
        slice={slice}
        pendingOnly={pendingOnly}
        productId={productId}
        onOpen={onOpen}
      />
    </QueryClientProvider>,
  );
  return { onOpen, invalidate };
}

function reportNativeRowActivation(event: MouseEvent | KeyboardEvent) {
  act(() => grid.options.onRowClicked?.({
    data: grid.rows.find((row) => row.key === '3|2026-01-01'),
    event,
  } as unknown as Parameters<NonNullable<GridOptions<TestRow>['onRowClicked']>>[0]));
}

describe('LineupGroupsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiPost.mockResolvedValue({ changed: 1 });
  });

  it('puts every header over its corresponding cell in customer/period order', () => {
    renderPanel({
      data: [
        ...rows,
        { ...rows[0], id: 4, planned_volume_units: 8 },
        { ...rows[0], id: 5, planned_volume_units: 10 },
        { ...rows[1], id: 6, planned_volume_units: 12 },
        { ...rows[0], id: 7, planned_volume_units: 14, approval_status: 'rejected' },
      ],
    });
    expect(screen.getAllByTestId(/^summary-/)).toHaveLength(2);
    expect(
      within(screen.getByTestId('group-headers'))
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual([
      'Customer', 'Period', 'Lines', 'Units', 'Pending', 'Approved', 'Rejected', 'Actions',
    ]);
    expect(grid.columns.map((column) => column.colId)).toEqual([
      'customer', 'period', 'lines', 'plannedUnits', 'pending', 'approved', 'rejected', 'actions',
    ]);

    const summary = within(screen.getByTestId('summary-3|2026-01-01'));
    expect(summary.getAllByRole('gridcell').map((cell) => cell.textContent)).toEqual([
      'Customer A', '26Q1', '6', '54', '3', '2', '1', 'OpenApproveReject',
    ]);
    expect(
      within(summary.getAllByRole('gridcell')[7])
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Open', 'Approve', 'Reject']);
    expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
  });

  it('fits essential columns at 1280px and keeps the action buttons pinned right', () => {
    renderPanel();
    // AppShell rail: 252px; WorkbenchCanvas horizontal padding: 40px.
    // Reserve another 40px for borders and the page/grid vertical scrollbars.
    const availableWidth = 1280 - 252 - 40 - 40;
    expect(grid.columns.every((column) => column.width != null)).toBe(true);
    const requiredWidth = grid.columns.reduce((total, column) => total + (column.width ?? 200), 0);
    expect(requiredWidth).toBeLessThanOrEqual(availableWidth);
    expect(grid.columns.find((column) => column.colId === 'actions')).toEqual(
      expect.objectContaining({
        width: 216,
        minWidth: 216,
        maxWidth: 216,
        pinned: 'right',
        lockPinned: true,
        resizable: false,
        suppressSizeToFit: true,
        filter: false,
      }),
    );
    expect(grid.options.suppressMovableColumns).toBe(true);
    expect(screen.getByTestId('lineup-group-open-3|2026-01-01')).toBeVisible();
    expect(screen.getByTestId('lineup-group-approve-3|2026-01-01')).toBeVisible();
    expect(screen.getByTestId('lineup-group-reject-3|2026-01-01')).toBeVisible();
  });

  it('aligns numeric cells with their right-aligned headers inside the flex grid', () => {
    renderPanel();
    for (const colId of ['lines', 'plannedUnits', 'pending', 'approved', 'rejected']) {
      expect(grid.columns.find((column) => column.colId === colId)?.type).toBe('numericColumn');
      expect(screen.getByTestId(`3|2026-01-01-${colId}`)).toHaveStyle({
        justifyContent: 'flex-end',
        textAlign: 'right',
        paddingLeft: '8px',
        paddingRight: '8px',
      });
    }
  });

  it('expands lines inside the same grid, switches groups, and closes them', () => {
    const { onOpen } = renderPanel();
    fireEvent.click(screen.getByTestId('summary-3|2026-01-01'));
    const detail = within(screen.getByTestId('group-grid')).getByTestId('lineup-group-detail-3|2026-01-01');
    expect(within(detail).getByTestId('detail-line-ids')).toHaveTextContent(/^1,2$/);
    expect(within(detail).getByTestId('lineup-group-workbench-3|2026-01-01')).toHaveAttribute(
      'href', '/commercial-planner?customer=3&period=2026-01-01',
    );
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ customerId: 3 }));

    fireEvent.click(screen.getByTestId('lineup-group-open-4|2026-01-01'));
    expect(screen.queryByTestId('lineup-group-detail-3|2026-01-01')).not.toBeInTheDocument();
    expect(screen.getByTestId('detail-line-ids')).toHaveTextContent(/^3$/);
    fireEvent.click(screen.getByRole('button', { name: 'Close lines' }));
    expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
  });

  it('activates Open and Close once when AG Grid also reports the native button click', () => {
    const { onOpen } = renderPanel();
    for (const expanded of [true, false]) {
      const button = screen.getByTestId('lineup-group-open-3|2026-01-01');
      let native: MouseEvent | undefined;
      button.addEventListener('click', (event) => { native = event as MouseEvent; }, { once: true });
      fireEvent.click(button);
      expect(native?.target).toBe(button);
      // AG Grid's native row event is delivered separately from React bubbling.
      // Calling it explicitly prevents the mock Stack.stopPropagation from hiding the bug.
      reportNativeRowActivation(native!);
      expect(screen.getByTestId('lineup-group-open-3|2026-01-01'))
        .toHaveAttribute('aria-expanded', String(expanded));
      if (expanded) expect(screen.getByTestId('detail-line-ids')).toHaveTextContent(/^1,2$/);
      else expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
    }
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it.each([
    ['button', false],
    ['button', true],
    ['a', true],
    ['role-button', true],
  ] as const)('ignores native row clicks originating from %s (nested=%s)', (kind, nested) => {
    const { onOpen } = renderPanel();
    const control = document.createElement(kind === 'role-button' ? 'div' : kind);
    if (kind === 'role-button') control.setAttribute('role', 'button');
    const target = nested ? control.appendChild(document.createElement('span')) : control;
    const event = new MouseEvent('click', { bubbles: true });
    target.dispatchEvent(event);
    expect(event.target).toBe(target);
    reportNativeRowActivation(event);
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
  });

  it.each(['Enter', ' '])('ignores button-origin %s row activation from the keyboard wrapper', (key) => {
    const { onOpen } = renderPanel();
    const control = document.createElement('button');
    const target = control.appendChild(document.createElement('span'));
    const event = new KeyboardEvent('keydown', { key, bubbles: true });
    target.dispatchEvent(event);
    reportNativeRowActivation(event);
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
  });

  it.each(['Enter', ' '])('preserves plain-cell %s row activation from the keyboard wrapper', (key) => {
    const { onOpen } = renderPanel();
    const target = document.createElement('span');
    const event = new KeyboardEvent('keydown', { key, bubbles: true });
    target.dispatchEvent(event);
    reportNativeRowActivation(event);
    expect(screen.getByTestId('detail-line-ids')).toHaveTextContent(/^1,2$/);
    reportNativeRowActivation(event);
    expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it.each(['approved', 'rejected'] as const)(
    'sends %s through the existing group endpoint and refreshes items',
    async (status) => {
      const { onOpen, invalidate } = renderPanel();
      const button = screen.getByTestId(
        `lineup-group-${status === 'approved' ? 'approve' : 'reject'}-3|2026-01-01`,
      );
      let native: MouseEvent | undefined;
      button.addEventListener('click', (event) => { native = event as MouseEvent; }, { once: true });
      fireEvent.click(button);
      reportNativeRowActivation(native!);
      await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
        '/api/v1/lineup/items/group-approval',
        {
          customer_id: 3,
          period_start: '2026-01-01',
          approval_status: status,
          only_pending: true,
        },
      ));
      await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lineup-items'] }));
      expect(onOpen).not.toHaveBeenCalled();
      expect(screen.queryByTestId('detail-line-ids')).not.toBeInTheDocument();
    },
  );

  it('disables both decisions when the group has no pending lines', () => {
    renderPanel();
    expect(screen.getByTestId('lineup-group-approve-4|2026-01-01')).toBeDisabled();
    expect(screen.getByTestId('lineup-group-reject-4|2026-01-01')).toBeDisabled();
  });

  it('keeps complete group totals while filtering product detail and pending groups', () => {
    renderPanel({
      slice: { customerId: 3, periodStart: '2026-01-01' },
      pendingOnly: true,
      productId: 11,
    });
    expect(screen.getAllByTestId(/^summary-/)).toHaveLength(1);
    expect(screen.getByTestId('3|2026-01-01-lines')).toHaveTextContent(/^2$/);
    expect(screen.getByTestId('3|2026-01-01-plannedUnits')).toHaveTextContent(/^10$/);
    expect(screen.getByTestId('detail-line-ids')).toHaveTextContent(/^1$/);
    expect(screen.getByText(/Line-up totals include all products/)).toBeInTheDocument();
  });

  it('does not show a group whose matching product has no pending line', () => {
    renderPanel({ pendingOnly: true, productId: 12 });
    expect(screen.queryAllByTestId(/^summary-/)).toHaveLength(0);
    expect(screen.getByText('0 line-ups match the current filters.')).toBeInTheDocument();
  });

  it('does not substitute customer codes for missing customer names', () => {
    renderPanel({ data: [{ ...rows[0], customer_name: null }] });
    expect(screen.getByTestId('3|2026-01-01-customer')).toHaveTextContent(/^Customer name not set$/);
    expect(screen.getByTestId('3|2026-01-01-customer')).not.toHaveTextContent('CODE-A');
  });

  it('shows a failed decision without hiding the line-ups', async () => {
    apiPost.mockRejectedValueOnce(new Error('Decision failed'));
    renderPanel();
    fireEvent.click(screen.getByTestId('lineup-group-approve-3|2026-01-01'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Decision failed');
    expect(screen.getAllByTestId(/^summary-/)).toHaveLength(2);
  });
});

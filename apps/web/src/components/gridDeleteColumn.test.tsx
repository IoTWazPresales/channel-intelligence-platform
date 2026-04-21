import type { ICellRendererParams } from 'ag-grid-community';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { gridDeleteColumn } from './gridDeleteColumn';

describe('gridDeleteColumn', () => {
  it('invokes onDelete when confirm is skipped', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const col = gridDeleteColumn(onDelete, { confirm: false });
    const Cell = col.cellRenderer!;
    const params = {
      data: { id: 42 },
    } as ICellRendererParams<{ id: number }>;
    const { getByRole } = renderWithProviders(<>{Cell(params)}</>);
    await user.click(getByRole('button', { name: 'Delete' }));
    expect(onDelete).toHaveBeenCalledWith(42);
  });

  it('respects busy state', () => {
    const col = gridDeleteColumn(vi.fn(), { confirm: false, busy: true });
    const Cell = col.cellRenderer!;
    const params = { data: { id: 1 } } as ICellRendererParams<{ id: number }>;
    const { getByRole } = renderWithProviders(<>{Cell(params)}</>);
    expect(getByRole('button', { name: 'Delete' })).toBeDisabled();
  });
});

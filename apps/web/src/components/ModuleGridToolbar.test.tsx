import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { ModuleGridToolbar } from './ModuleGridToolbar';

describe('ModuleGridToolbar', () => {
  it('invokes refresh and clear handlers', async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    const onClearAll = vi.fn();
    const { getByRole } = renderWithProviders(
      <ModuleGridToolbar onRefresh={onRefresh} onClearAll={onClearAll} />
    );
    await user.click(getByRole('button', { name: 'Refresh' }));
    await user.click(getByRole('button', { name: 'Clear all rows' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('renders Import Center link when importsHref is set', () => {
    const { getByRole } = renderWithProviders(<ModuleGridToolbar importsHref="/admin/imports" />);
    expect(getByRole('link', { name: 'Import Center' })).toHaveAttribute('href', '/admin/imports');
  });
});

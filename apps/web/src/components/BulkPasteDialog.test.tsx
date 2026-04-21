import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { BulkPasteDialog } from './BulkPasteDialog';

describe('BulkPasteDialog', () => {
  it('disables submit when value is blank', () => {
    const { getByRole } = renderWithProviders(
      <BulkPasteDialog
        open
        title="Import"
        value=""
        onChange={vi.fn()}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />
    );
    expect(getByRole('button', { name: 'Import' })).toBeDisabled();
  });

  it('calls onSubmit when value is present', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const { getByRole } = renderWithProviders(
      <BulkPasteDialog
        open
        title="Import"
        value="a,b"
        onChange={vi.fn()}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );
    await user.click(getByRole('button', { name: 'Import' }));
    expect(onSubmit).toHaveBeenCalled();
  });
});

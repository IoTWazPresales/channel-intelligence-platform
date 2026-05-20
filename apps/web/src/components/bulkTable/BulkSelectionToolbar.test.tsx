import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { BulkSelectionToolbar } from './BulkSelectionToolbar';

describe('BulkSelectionToolbar', () => {
  it('shows only enter bulk mode in normal mode (no selection count)', () => {
    render(
      <BulkSelectionToolbar
        mode="normal"
        selectedCount={0}
        visibleRowCount={5}
        onEnterSelectionMode={vi.fn()}
        onExitSelectionMode={vi.fn()}
        onSelectAllVisible={vi.fn()}
        onDeselectAll={vi.fn()}
        onPreviewDangerAction={vi.fn()}
      />
    );
    expect(screen.queryByTestId('bulk-selection-toolbar')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /bulk actions/i })).toBeInTheDocument();
  });

  it('shows toolbar with selection count and disabled preview when none selected', () => {
    render(
      <BulkSelectionToolbar
        mode="selecting"
        selectedCount={0}
        visibleRowCount={3}
        onEnterSelectionMode={vi.fn()}
        onExitSelectionMode={vi.fn()}
        onSelectAllVisible={vi.fn()}
        onDeselectAll={vi.fn()}
        onPreviewDangerAction={vi.fn()}
      />
    );
    expect(screen.getByTestId('bulk-selection-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('bulk-selection-count')).toHaveTextContent('0 selected');
    expect(screen.getByTestId('bulk-preview-danger')).toBeDisabled();
  });

  it('updates preview enabled state when selection count increases', async () => {
    const user = userEvent.setup();
    const onPreview = vi.fn();
    const { rerender } = render(
      <BulkSelectionToolbar
        mode="selecting"
        selectedCount={0}
        visibleRowCount={2}
        onEnterSelectionMode={vi.fn()}
        onExitSelectionMode={vi.fn()}
        onSelectAllVisible={vi.fn()}
        onDeselectAll={vi.fn()}
        onPreviewDangerAction={onPreview}
      />
    );
    expect(screen.getByTestId('bulk-preview-danger')).toBeDisabled();
    rerender(
      <BulkSelectionToolbar
        mode="selecting"
        selectedCount={2}
        visibleRowCount={2}
        onEnterSelectionMode={vi.fn()}
        onExitSelectionMode={vi.fn()}
        onSelectAllVisible={vi.fn()}
        onDeselectAll={vi.fn()}
        onPreviewDangerAction={onPreview}
      />
    );
    const preview = screen.getByTestId('bulk-preview-danger');
    expect(preview).not.toBeDisabled();
    await user.click(preview);
    expect(onPreview).toHaveBeenCalledTimes(1);
  });
});

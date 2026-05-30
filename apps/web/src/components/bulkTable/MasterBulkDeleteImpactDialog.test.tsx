import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MasterBulkDeleteImpactDialog, type MasterBulkDeletePreview } from './MasterBulkDeleteImpactDialog';

const basePreview: MasterBulkDeletePreview = {
  entity_type: 'customers',
  entity_ids: [1, 2],
  missing_entity_ids: [],
  rows: [
    { id: 1, label: 'CUST-1', references: [], blocked: false },
    {
      id: 2,
      label: 'CUST-2',
      references: [{ label: 'Sell-out', count: 3 }],
      blocked: true,
    },
  ],
  blocked_count: 1,
  deletable_count: 1,
  deletable_ids: [1],
};

describe('MasterBulkDeleteImpactDialog', () => {
  it('shows blocked rows and requires acknowledgement', () => {
    const onConfirm = vi.fn();
    render(
      <MasterBulkDeleteImpactDialog
        open
        busy={false}
        preview={basePreview}
        entityLabel="customers"
        impactAcknowledged={false}
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    );
    expect(screen.getByTestId('master-bulk-delete-dialog')).toBeVisible();
    expect(screen.getByTestId('master-bulk-blocked-alert')).toBeVisible();
    expect(screen.getByTestId('master-bulk-confirm-delete')).toBeDisabled();
    fireEvent.click(screen.getByTestId('master-bulk-impact-ack'));
  });
});

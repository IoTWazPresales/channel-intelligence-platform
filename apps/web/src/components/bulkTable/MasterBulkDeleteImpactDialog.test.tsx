import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HttpConflictError } from '@/lib/api';

import {
  MasterBulkDeleteImpactDialog,
  formatMasterBulkDeleteConflict,
  type MasterBulkDeletePreview,
} from './MasterBulkDeleteImpactDialog';

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

  it('shows 409 reference detail when confirm fails', async () => {
    const onConfirm = vi.fn().mockRejectedValue(
      new HttpConflictError('Customer could not be deleted.', [
        { label: 'DSI import staging (resolved customer)', count: 2 },
      ])
    );
    render(
      <MasterBulkDeleteImpactDialog
        open
        busy={false}
        preview={basePreview}
        entityLabel="customers"
        impactAcknowledged
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    );
    fireEvent.click(screen.getByTestId('master-bulk-confirm-delete'));
    expect(await screen.findByTestId('master-bulk-confirm-error')).toBeVisible();
    expect(screen.getByText(/DSI import staging/)).toBeVisible();
  });

  it('formatMasterBulkDeleteConflict includes reference lines', () => {
    const msg = formatMasterBulkDeleteConflict(
      new HttpConflictError('Blocked', [{ label: 'Sell-out', count: 1 }])
    );
    expect(msg).toContain('Sell-out');
    expect(msg).toContain('Blocked');
  });
});

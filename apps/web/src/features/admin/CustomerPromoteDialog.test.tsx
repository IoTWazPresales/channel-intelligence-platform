import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import * as apiLib from '@/lib/api';

import {
  CustomerPromoteDialog,
  customerPromoteActionVisible,
} from './CustomerPromoteDialog';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof apiLib>('@/lib/api');
  return {
    ...actual,
    apiPost: vi.fn(),
  };
});

const apiPost = apiLib.apiPost as unknown as ReturnType<typeof vi.fn>;

function renderDialog(props: Partial<ComponentProps<typeof CustomerPromoteDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CustomerPromoteDialog
        open
        customer={{
          id: 10,
          customer_code: 'TMP-CUST-ABC',
          customer_name: 'Acme',
          customer_status: 'unverified',
        }}
        onClose={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  );
}

describe('customerPromoteActionVisible', () => {
  it('shows for TMP-CUST only', () => {
    expect(customerPromoteActionVisible({ customer_code: 'TMP-CUST-1' })).toBe(true);
    expect(customerPromoteActionVisible({ customer_code: 'REAL-1' })).toBe(false);
    expect(
      customerPromoteActionVisible({ customer_code: 'TMP-CUST-1', merged_into_customer_id: 9 })
    ).toBe(false);
  });
});

describe('CustomerPromoteDialog', () => {
  beforeEach(() => {
    apiPost.mockReset();
  });

  it('preview shows both warnings and keeps confirm disabled until ack', async () => {
    apiPost.mockResolvedValueOnce({
      dry_run: true,
      applied: false,
      can_confirm: true,
      customer_id: 10,
      new_code: 'ACME-001',
      promote_target_status: 'active',
      eligibility: {
        eligible: true,
        reasons: [],
        admin_mint_edge: false,
        old_code: 'TMP-CUST-ABC',
        old_status: 'unverified',
      },
      collision: null,
      warnings: [
        'Leaving unverified stops provisional reuse for this row; future imports may mint a duplicate.',
        'Future bulk upserts that still send the old TMP code will create a NEW customer row; prefer a source-token alias or update source files.',
      ],
    });

    renderDialog();
    fireEvent.change(screen.getByTestId('promote-new-code'), { target: { value: 'ACME-001' } });
    fireEvent.click(screen.getByTestId('promote-preview-btn'));

    await waitFor(() => expect(screen.getByTestId('promote-preview')).toBeInTheDocument());
    expect(screen.getAllByTestId('promote-warning')).toHaveLength(2);
    expect(screen.getByTestId('promote-confirm-btn')).toBeDisabled();

    fireEvent.click(screen.getByTestId('promote-ack'));
    expect(screen.getByTestId('promote-confirm-btn')).not.toBeDisabled();
  });

  it('collision disables confirm', async () => {
    apiPost.mockResolvedValueOnce({
      dry_run: true,
      applied: false,
      can_confirm: false,
      customer_id: 10,
      new_code: 'ACME-001',
      promote_target_status: 'active',
      eligibility: {
        eligible: true,
        reasons: [],
        admin_mint_edge: false,
        old_code: 'TMP-CUST-ABC',
        old_status: 'unverified',
      },
      collision: {
        customer_id: 20,
        code: 'ACME-001',
        customer_status: 'active',
        merged_into_customer_id: null,
        note: 'blocked',
      },
      warnings: [],
    });

    renderDialog();
    fireEvent.change(screen.getByTestId('promote-new-code'), { target: { value: 'ACME-001' } });
    fireEvent.click(screen.getByTestId('promote-preview-btn'));
    await waitFor(() => expect(screen.getByTestId('promote-collision')).toBeInTheDocument());
    expect(screen.getByTestId('promote-confirm-btn')).toBeDisabled();
  });

  it('admin_mint_edge shows caution', async () => {
    apiPost.mockResolvedValueOnce({
      dry_run: true,
      applied: false,
      can_confirm: true,
      customer_id: 10,
      new_code: 'ACME-001',
      promote_target_status: 'active',
      eligibility: {
        eligible: true,
        reasons: [],
        admin_mint_edge: true,
        old_code: 'TMP-CUST-ABC',
        old_status: 'active',
      },
      collision: null,
      warnings: ['bulk risk'],
    });

    renderDialog({
      customer: {
        id: 10,
        customer_code: 'TMP-CUST-ABC',
        customer_name: 'Acme',
        customer_status: 'active',
      },
    });
    fireEvent.change(screen.getByTestId('promote-new-code'), { target: { value: 'ACME-001' } });
    fireEvent.click(screen.getByTestId('promote-preview-btn'));
    await waitFor(() => expect(screen.getByTestId('promote-admin-mint-edge')).toBeInTheDocument());
  });

  it('confirm success calls confirm:true and shows old→new', async () => {
    apiPost
      .mockResolvedValueOnce({
        dry_run: true,
        applied: false,
        can_confirm: true,
        customer_id: 10,
        new_code: 'ACME-001',
        promote_target_status: 'active',
        eligibility: {
          eligible: true,
          reasons: [],
          admin_mint_edge: false,
          old_code: 'TMP-CUST-ABC',
          old_status: 'unverified',
        },
        collision: null,
        warnings: ['w1', 'w2'],
      })
      .mockResolvedValueOnce({
        applied: true,
        customer_id: 10,
        old_code: 'TMP-CUST-ABC',
        new_code: 'ACME-001',
        old_status: 'unverified',
        new_status: 'active',
        promoted_at: '2026-07-10T00:00:00Z',
      });

    renderDialog();
    fireEvent.change(screen.getByTestId('promote-new-code'), { target: { value: 'ACME-001' } });
    fireEvent.change(screen.getByTestId('promote-note'), { target: { value: 'ok' } });
    fireEvent.click(screen.getByTestId('promote-preview-btn'));
    await waitFor(() => expect(screen.getByTestId('promote-ack')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('promote-ack'));
    fireEvent.click(screen.getByTestId('promote-confirm-btn'));

    await waitFor(() => expect(screen.getByTestId('promote-success')).toBeInTheDocument());
    expect(apiPost).toHaveBeenLastCalledWith('/api/v1/customers/10/promote', {
      new_code: 'ACME-001',
      confirm: true,
      note: 'ok',
    });
    expect(screen.getByTestId('promote-success').textContent).toMatch(/TMP-CUST-ABC.*ACME-001/);
  });

  it('surfaces API error message', async () => {
    apiPost.mockRejectedValueOnce(new Error('new_code already owned by customer_id=20'));
    renderDialog();
    fireEvent.change(screen.getByTestId('promote-new-code'), { target: { value: 'ACME-001' } });
    fireEvent.click(screen.getByTestId('promote-preview-btn'));
    await waitFor(() => expect(screen.getByTestId('promote-error')).toBeInTheDocument());
    expect(screen.getByTestId('promote-error').textContent).toMatch(/already owned/);
  });
});

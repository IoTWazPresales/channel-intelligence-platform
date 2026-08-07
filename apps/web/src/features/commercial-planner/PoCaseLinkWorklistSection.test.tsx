/**
 * Unit 6a — PoCaseLinkWorklistSection mounts ResolutionWorklist with Unlink only (no target picker).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PoCaseLinkWorklistSection } from './PoCaseLinkWorklistSection';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiPost: (...args: unknown[]) => apiPostMock(...args),
}));

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PoCaseLinkWorklistSection />
    </QueryClientProvider>,
  );
}

describe('PoCaseLinkWorklistSection', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    apiGetMock.mockImplementation((path: string) => {
      if (path.includes('/case-po-links')) {
        return Promise.resolve({
          total: 1,
          links: [
            {
              link_id: 99,
              item_key: '10:5',
              case_id: 10,
              commercial_status: 'po_pending',
              purchase_order_id: 5,
              po_number: 'PO99',
              po_number_norm: 'PO99',
              carried_under_d032: false,
              row_class: 'active',
              po_link_count: 1,
              bulk_protection: {
                selection_protected: true,
                requires_allow_protected: true,
                reasons: ['confirmed_po_links'],
                contested: false,
              },
            },
          ],
        });
      }
      return Promise.reject(new Error(path));
    });
  });

  it('renders unlink control and no target picker', async () => {
    renderSection();
    expect(await screen.findByTestId('po-case-link-section')).toBeInTheDocument();
    expect(await screen.findByTestId('po-case-link-row-10:5')).toBeInTheDocument();
    expect(screen.getByTestId('po-case-link-unlink-10:5')).toBeInTheDocument();
    expect(screen.queryByTestId('merge-promote-target-picker')).not.toBeInTheDocument();
  });

  it('posts unlink with reason and allow_protected for protected case', async () => {
    apiPostMock.mockResolvedValue({
      unlinked_count: 1,
      reason: 'wrong link',
      results: [
        {
          case_id: 10,
          purchase_order_id: 5,
          before_status: 'po_pending',
          after_status: 'draft_imported',
          before_po_count: 1,
          after_po_count: 0,
        },
      ],
    });
    const user = userEvent.setup();
    renderSection();
    await screen.findByTestId('po-case-link-unlink-10:5');
    await user.click(screen.getByTestId('po-case-link-unlink-10:5'));
    expect(await screen.findByTestId('po-case-link-unlink-dialog')).toBeInTheDocument();
    await user.click(screen.getByTestId('po-case-link-allow-protected'));
    await user.click(screen.getByTestId('po-case-link-unlink-submit'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        '/api/v1/commercial-planner/lineup/case-po-links/unlink',
        expect.objectContaining({
          reason: 'wrong link',
          items: [expect.objectContaining({ case_id: 10, purchase_order_id: 5, allow_protected: true })],
        }),
      );
    });
    expect(await screen.findByTestId('po-case-link-success')).toBeInTheDocument();
  });
});

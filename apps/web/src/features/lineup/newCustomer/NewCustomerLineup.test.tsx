import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { NewCustomerLineup } from './NewCustomerLineup';
import type { Proposal } from './types';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiPost: (...args: unknown[]) => apiPostMock(...args),
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const masterProposal: Proposal = {
  customer: { id: 7, code: 'C-7', name: 'Seven Stores' },
  period_start: '2026-10-01',
  period_label: '2026 Q4',
  source: 'previous_lineups',
  fallback: 'master',
  periods_used: ['2026-10-01', '2026-07-01'],
  basis: 'This customer has no line-up rows of its own, so the master line-up is used.',
  line_count: 2,
  lines: [
    {
      product_id: 11,
      sku: 'SKU-11',
      label: 'Alpha',
      seed_source: 'previous_lineups',
      evidence: { kind: 'previous_lineups', scope: 'master', periods: ['2026-10-01'] },
    },
    {
      product_id: 12,
      sku: 'SKU-12',
      label: 'Beta',
      seed_source: 'previous_lineups',
      evidence: { kind: 'previous_lineups', scope: 'master', periods: ['2026-07-01'] },
    },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <NewCustomerLineup />
    </QueryClientProvider>,
  );
}

async function chooseCustomer() {
  await screen.findByRole('option', { name: 'Seven Stores' });
  fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '7' } });
}

describe('NewCustomerLineup', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('reporting-customers')) {
        return { customers: [{ id: 7, name: 'Seven Stores' }] };
      }
      return masterProposal;
    });
  });

  it('explains both seed sources and the own-versus-master rule before anything is loaded', async () => {
    renderPage();
    expect(await screen.findByText(/Master-catalogue items with a PM bottom cost/)).toBeTruthy();
    expect(screen.getByText(/SKUs from the previous line-ups/)).toBeTruthy();
    expect(screen.getByText(/own 3 most recent line-up periods/i)).toBeTruthy();
    expect(screen.getByText(/master line-up/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull();
  });

  it('loads the proposal for the chosen source and shows the fallback used and the periods', async () => {
    renderPage();
    await chooseCustomer();
    fireEvent.click(screen.getByLabelText(/SKUs from the previous line-ups/));
    fireEvent.click(screen.getByRole('button', { name: /show proposal/i }));
    expect(await screen.findByText('Alpha')).toBeTruthy();
    expect(screen.getByText('Master line-up, all customers: 2026 Q4, 2026 Q3')).toBeTruthy();
    expect(screen.getByText('In line-ups: 2026 Q4')).toBeTruthy();
    const proposalCall = apiGetMock.mock.calls.map((c) => String(c[0])).find((u) => u.includes('/proposal'));
    expect(proposalCall).toMatch(/\/api\/v1\/lineup\/new-customer\/7\/proposal\?source=previous_lineups&period_start=\d{4}-\d{2}-01/);
  });

  it('approves only the ticked lines and then offers the line-up', async () => {
    apiPostMock.mockResolvedValue({
      approved_count: 1,
      commercial_case_id: 55,
      created: [{ item_id: 1, product_id: 12, sku: 'SKU-12' }],
    });
    renderPage();
    await chooseCustomer();
    fireEvent.click(screen.getByLabelText(/SKUs from the previous line-ups/));
    fireEvent.click(screen.getByRole('button', { name: /show proposal/i }));
    await screen.findByText('Alpha');

    fireEvent.click(screen.getByLabelText('Include SKU-11'));
    expect(screen.getByText('1 of 2 lines selected')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /approve 1 line/i }));

    await waitFor(() => expect(apiPostMock).toHaveBeenCalledTimes(1));
    const [path, body] = apiPostMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/api/v1/lineup/new-customer/7/approve');
    expect(body).toMatchObject({ source: 'previous_lineups', product_ids: [12] });
    expect(await screen.findByText(/Approved 1 line/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /open the line-up cases/i }).getAttribute('href')).toBe('/lineup/cases');
  });

  it('disables approval when every line is unticked', async () => {
    renderPage();
    await chooseCustomer();
    fireEvent.click(screen.getByLabelText(/SKUs from the previous line-ups/));
    fireEvent.click(screen.getByRole('button', { name: /show proposal/i }));
    await screen.findByText('Alpha');
    fireEvent.click(screen.getByLabelText('Include SKU-11'));
    fireEvent.click(screen.getByLabelText('Include SKU-12'));
    const button = screen.getByRole('button', { name: /^approve/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('shows the refusal message when the customer is not a reporting customer', async () => {
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('reporting-customers')) return { customers: [{ id: 7, name: 'Seven Stores' }] };
      throw new Error('Line-ups are only built for reporting customers (reports expected).');
    });
    renderPage();
    await chooseCustomer();
    fireEvent.click(screen.getByLabelText(/Master-catalogue items with a PM bottom cost/));
    fireEvent.click(screen.getByRole('button', { name: /show proposal/i }));
    expect(await screen.findByText(/only built for reporting customers/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^approve/i })).toBeNull();
  });

  it('says so when the customer list is empty', async () => {
    apiGetMock.mockImplementation(async () => ({ customers: [] }));
    renderPage();
    expect(await screen.findByText(/No reporting customers/)).toBeTruthy();
  });
});

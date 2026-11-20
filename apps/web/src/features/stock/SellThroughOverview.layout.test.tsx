import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SellThroughOverview } from './SellThroughOverview';
import type { SellThroughFilterOptions } from './sellThroughTypes';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const options: SellThroughFilterOptions = {
  customers: [], business_units: [], categories: [], series: [],
  first_period: null, last_period: null, presets: [], today: '2026-11-20',
  calendar: { type: 'gregorian', year: { label: '2026', start: '2026-01-01', end: '2026-12-31' } },
  vat: 'ex_vat', vat_rate_pct: 0,
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => options),
  apiPost: vi.fn(),
  safeDisplayError: (error: unknown) => String(error),
}));

describe('Sell-through filter layout', () => {
  it('keeps the wrapping date/filter bar in document flow before and after scrolling', async () => {
    const { container } = renderWithProviders(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SellThroughOverview />
      </QueryClientProvider>,
    );
    const bar = await screen.findByRole('toolbar', { name: 'Sell-through filters' });
    expect(screen.getByLabelText('From')).toBeInTheDocument();
    expect(screen.getByLabelText('To')).toBeInTheDocument();
    expect(getComputedStyle(bar).position).toBe('static');
    expect(getComputedStyle(bar).flexWrap).toBe('wrap');
    fireEvent.scroll(container, { target: { scrollTop: 400 } });
    expect(getComputedStyle(bar).position).toBe('static');
    expect(getComputedStyle(bar).zIndex).not.toBe('3');
  });
});

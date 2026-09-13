import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ForecastHonesty, SellthroughHonesty } from './StockThinLenses';

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({
    data_unavailable: false,
    sellthrough: {
      title: 'Retailer sell-through for W37 not yet imported',
      body: 'cip CST grain',
    },
    forecast: {
      title: 'Forecasts need 8 weeks of applied sell-out',
      body: '0 of 8 weeks',
    },
  })),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('StockThinLenses', () => {
  it('renders sell-through honesty with remapped workspace href', async () => {
    render(wrap(<SellthroughHonesty />));
    expect(await screen.findByTestId('sellthrough-honesty')).toBeInTheDocument();
    expect(screen.getByText('Retailer sell-through for W37 not yet imported')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open workspace' })).toHaveAttribute(
      'href',
      '/channel-intelligence/workspace',
    );
  });

  it('renders forecast honesty with remapped workspace href', async () => {
    render(wrap(<ForecastHonesty />));
    expect(await screen.findByTestId('forecast-honesty')).toBeInTheDocument();
    expect(screen.getByText('Forecasts need 8 weeks of applied sell-out')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open workspace' })).toHaveAttribute('href', '/forecasts/workspace');
  });
});

import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import PricingPage from './page';

describe('retired Recorded prices page', () => {
  it('explains the replacement sources and links to their screens', () => {
    renderWithProviders(<PricingPage />);

    expect(
      screen.getByText(
        'Recorded prices was retired. Prices now come from the line-up retail price and the latest shelf price seen on customer listings',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Line-up' })).toHaveAttribute('href', '/lineup');
    expect(screen.getByRole('link', { name: 'Customer listings' })).toHaveAttribute(
      'href',
      '/listing-capture?tab=registry',
    );
    expect(screen.queryByRole('button', { name: /add|upload|clear|delete|save/i })).not.toBeInTheDocument();
  });
});

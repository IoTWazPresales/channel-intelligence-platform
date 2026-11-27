import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DomainHeader } from './DomainHeader';

describe('DomainHeader', () => {
  it('renders the page title as an h1', () => {
    const { getByRole } = renderWithProviders(<DomainHeader title="Promotions" />);
    expect(getByRole('heading', { level: 1, name: 'Promotions' })).toBeInTheDocument();
  });
});

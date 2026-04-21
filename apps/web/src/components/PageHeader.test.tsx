import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders title and crumb labels', () => {
    const { getByText } = renderWithProviders(
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Catalog' }]} title="Products" />
    );
    expect(getByText('Products', { selector: 'h5' })).toBeInTheDocument();
    expect(getByText('Admin')).toBeInTheDocument();
    expect(getByText('Catalog')).toBeInTheDocument();
  });

  it('renders link crumb when href is set', () => {
    const { getByRole } = renderWithProviders(
      <PageHeader crumbs={[{ label: 'Home', href: '/' }]} title="T" />
    );
    const link = getByRole('link', { name: 'Home' });
    expect(link).toHaveAttribute('href', '/');
  });
});

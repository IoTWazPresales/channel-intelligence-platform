import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders title and crumb labels', () => {
    const { getByText } = renderWithProviders(
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Catalog' }]} title="Products" />
    );
    // Requirement changed: the dashboard-v2 mock-up title is an h1. Warren 26 Nov: "Yes".
    expect(getByText('Products', { selector: 'h1' })).toBeInTheDocument();
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

  it('omits the breadcrumb row when there are no crumbs', () => {
    const { queryByRole, getByRole } = renderWithProviders(<PageHeader crumbs={[]} title="What CIP does" />);
    expect(getByRole('heading', { level: 1, name: 'What CIP does' })).toBeInTheDocument();
    expect(queryByRole('navigation')).not.toBeInTheDocument();
  });
});

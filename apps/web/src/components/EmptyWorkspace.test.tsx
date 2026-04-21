import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { EmptyWorkspace } from './EmptyWorkspace';

describe('EmptyWorkspace', () => {
  it('renders title, description, and links', () => {
    const { getByRole, getByText } = renderWithProviders(
      <EmptyWorkspace
        title="No rows"
        description="Import something"
        primary={{ label: 'Start', href: '/getting-started' }}
        secondary={{ label: 'Admin', href: '/admin' }}
      />
    );
    expect(getByText('No rows')).toBeInTheDocument();
    expect(getByText('Import something')).toBeInTheDocument();
    expect(getByRole('link', { name: 'Start' })).toHaveAttribute('href', '/getting-started');
    expect(getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin');
  });
});

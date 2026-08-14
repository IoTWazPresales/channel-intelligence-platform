import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

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

  it('fires onClick for a compute-style primary action', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { getByRole } = renderWithProviders(
      <EmptyWorkspace
        title="No rows"
        description="Compute first"
        primary={{ label: 'Compute from history', onClick }}
      />
    );
    await user.click(getByRole('button', { name: 'Compute from history' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

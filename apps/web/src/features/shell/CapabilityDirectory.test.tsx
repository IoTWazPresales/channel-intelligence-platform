import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: undefined }),
}));

import { CapabilityDirectory } from './CapabilityDirectory';

describe('CapabilityDirectory', () => {
  it('renders the page title as the theme h1', () => {
    const { getByRole } = renderWithProviders(<CapabilityDirectory />);
    expect(getByRole('heading', { level: 1, name: 'What CIP does' })).toBeInTheDocument();
  });
});

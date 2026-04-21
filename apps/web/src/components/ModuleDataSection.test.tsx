import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { ModuleDataSection } from './ModuleDataSection';

const emptyProps = {
  title: 'Empty',
  description: 'Nothing here',
} as const;

describe('ModuleDataSection', () => {
  it('shows loading state', () => {
    const { getByRole } = renderWithProviders(
      <ModuleDataSection isLoading isEmpty={false} empty={emptyProps}>
        <div>child</div>
      </ModuleDataSection>
    );
    expect(getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows error with retry', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { getByRole } = renderWithProviders(
      <ModuleDataSection isError error={new Error('boom')} onRetry={onRetry} isEmpty={false} empty={emptyProps}>
        <div>child</div>
      </ModuleDataSection>
    );
    expect(getByRole('alert')).toHaveTextContent('boom');
    await user.click(getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('renders children when data is ready', () => {
    const { getByText } = renderWithProviders(
      <ModuleDataSection isEmpty={false} empty={emptyProps}>
        <div>grid-body</div>
      </ModuleDataSection>
    );
    expect(getByText('grid-body')).toBeInTheDocument();
  });
});

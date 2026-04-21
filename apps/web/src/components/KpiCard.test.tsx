import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { KpiCard } from './KpiCard';

describe('KpiCard', () => {
  it('renders label and value', () => {
    const { getByText } = renderWithProviders(<KpiCard label="Open" value={12} />);
    expect(getByText('Open')).toBeInTheDocument();
    expect(getByText('12')).toBeInTheDocument();
  });

  it('invokes onExplain when card is clicked', async () => {
    const user = userEvent.setup();
    const onExplain = vi.fn();
    const { getByRole } = renderWithProviders(<KpiCard label="K" value="1" onExplain={onExplain} />);
    await user.click(getByRole('button'));
    expect(onExplain).toHaveBeenCalledTimes(1);
  });
});

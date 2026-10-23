import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useUiStore } from '@/stores/uiStore';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import DesignLabChartsPage from './page';

describe('design-lab charts fixture page (N-0114)', () => {
  it('renders every section with the real shared charts, and the mode toggle switches light and dark', () => {
    renderWithProviders(<DesignLabChartsPage />);
    const page = screen.getByTestId('design-lab-charts');
    for (const title of ['1. Long customer names, 37 categories', '2. Few short categories', '3. Vertical wrap case', '6. Pie, nine slices', '8. One series over 52 weeks', '9. Edge cases']) {
      expect(within(page).getByText(title)).toBeInTheDocument();
    }
    expect(within(page).getAllByText('Top 10 of 37').length).toBeGreaterThan(0);
    expect(within(page).getByText('Top 5 of 9 shown · shares are of the full total')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Light' }));
    expect(useUiStore.getState().colorMode).toBe('light');
    fireEvent.click(screen.getByRole('button', { name: 'Dark' }));
    expect(useUiStore.getState().colorMode).toBe('dark');
  });
});

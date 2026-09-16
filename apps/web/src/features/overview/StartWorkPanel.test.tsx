import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StartWorkPanel } from './StartWorkPanel';

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'u1', role: 'admin' } }),
}));

describe('StartWorkPanel', () => {
  it('renders start jobs as action cards, not blotter rows or import-center tiles', () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <StartWorkPanel />
      </ThemeProvider>
    );
    expect(screen.getByTestId('start-work')).toBeInTheDocument();
    expect(screen.getByTestId('start-work-cards')).toBeInTheDocument();
    expect(screen.getByText('Start work')).toBeInTheDocument();
    expect(screen.getByTestId('start-work-create-lineup')).toHaveTextContent('Import a lineup');
    expect(screen.getByRole('link', { name: /Import a lineup/i })).toHaveAttribute('href', '/admin/imports?unified=1');
    expect(screen.getAllByText('Start').length).toBeGreaterThanOrEqual(7);
    expect(screen.queryByText('distributor_inventory')).not.toBeInTheDocument();
  });
});

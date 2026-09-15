import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StartWorkPanel } from './StartWorkPanel';

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'u1', role: 'admin' } }),
}));

describe('StartWorkPanel', () => {
  it('lists start jobs as Overview rows, not import-center tiles', () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <StartWorkPanel />
      </ThemeProvider>
    );
    expect(screen.getByTestId('start-work')).toBeInTheDocument();
    expect(screen.getByText('Start work')).toBeInTheDocument();
    expect(screen.getByTestId('start-work-create-lineup')).toHaveTextContent('Import a lineup');
    expect(screen.getByRole('link', { name: /Import a lineup/i })).toHaveAttribute('href', '/admin/imports?unified=1');
    expect(screen.queryByRole('button', { name: /Import a lineup/i })).not.toBeInTheDocument();
  });
});

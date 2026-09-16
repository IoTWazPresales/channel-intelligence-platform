'use client';

import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StartWorkLaunch } from './StartWorkLaunch';

function renderLaunch(role: string | null) {
  return render(
    <ThemeProvider theme={createTheme()}>
      <StartWorkLaunch role={role} />
    </ThemeProvider>,
  );
}

describe('StartWorkLaunch', () => {
  it('admin sees seven action cards with governed hrefs', () => {
    renderLaunch('admin');
    expect(screen.getByTestId('start-work-cards').querySelectorAll('a')).toHaveLength(7);
    expect(screen.getByRole('link', { name: /Import a lineup/i })).toHaveAttribute('href', '/admin/imports?unified=1');
    expect(screen.getByRole('link', { name: /Create promotion plan/i })).toHaveAttribute(
      'href',
      '/promotions?propose=1',
    );
    expect(screen.getByRole('link', { name: /Work the steward queue/i })).toHaveAttribute('href', '/admin/mappings');
    expect(screen.getAllByText('Plan').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Data').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Funding')).toBeInTheDocument();
  });

  it('viewer sees the empty state, not a list of jobs', () => {
    renderLaunch('viewer');
    expect(screen.queryByTestId('start-work-cards')).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing this role can start/i)).toBeInTheDocument();
  });

  it('maps lab hrefs when hrefFor is supplied', () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <StartWorkLaunch role="steward" hrefFor={(v) => `/design-lab/${v.id}`} />
      </ThemeProvider>,
    );
    expect(screen.getByRole('link', { name: /Import a lineup/i })).toHaveAttribute(
      'href',
      '/design-lab/create-lineup',
    );
    expect(screen.queryByRole('link', { name: /Settle a case/i })).not.toBeInTheDocument();
  });
});

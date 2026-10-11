import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { HeadlineFigure } from './HeadlineFigure';

describe('HeadlineFigure', () => {
  it('renders existing callers unchanged (label, value, unit, delta, caption)', () => {
    renderWithProviders(
      <HeadlineFigure label="Network cover" value="5.4" unit="weeks" delta={{ text: '0.6w', direction: 'down' }} caption="220 pairs" testId="t" />,
    );
    expect(screen.getByText('Network cover')).toBeInTheDocument();
    expect(screen.getByText('5.4')).toBeInTheDocument();
    expect(screen.getByText('weeks')).toBeInTheDocument();
    expect(screen.getByText('▼ 0.6w')).toBeInTheDocument();
    expect(screen.getByText('220 pairs')).toBeInTheDocument();
    expect(screen.getByTestId('t')).toHaveAttribute('data-state', 'ready');
    expect(screen.queryByTestId('sparkline')).toBeNull();
  });

  it('shows delta period, target and sparkline for the mockup tile', () => {
    renderWithProviders(
      <HeadlineFigure
        lead
        label="Network weeks of cover"
        value="5.4"
        unit="weeks"
        delta={{ text: '0.6w', direction: 'down', period: 'W38' }}
        target="target ≥ 4 weeks"
        sparkline={{ values: [6.3, 6.1, 5.4], label: '12-week trend, 6.3 to 5.4 weeks' }}
      />,
    );
    expect(screen.getByText('▼ 0.6w vs W38')).toBeInTheDocument();
    expect(screen.getByText('target ≥ 4 weeks')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '12-week trend, 6.3 to 5.4 weeks' })).toBeInTheDocument();
  });

  it('loading hides the value and marks the tile busy', () => {
    renderWithProviders(<HeadlineFigure label="Sell-out" value="15 560" state="loading" testId="t" />);
    expect(screen.queryByText('15 560')).toBeNull();
    expect(screen.getByTestId('t')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('empty shows a dash and the reason in plain words', () => {
    renderWithProviders(<HeadlineFigure label="Fill vs plan" value="0.9" unit="%" state="empty" stateNote="No plan lines in P09." />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('0.9')).toBeNull();
    expect(screen.getByText('No plan lines in P09.')).toBeInTheDocument();
  });

  it('stale keeps the value and says why in text, not colour only', () => {
    renderWithProviders(<HeadlineFigure label="Cover" value="5.4" state="stale" stateNote="Data as of 1 Aug 2026." />);
    expect(screen.getByText('5.4')).toBeInTheDocument();
    expect(screen.getByTestId('figure-stale-note')).toHaveTextContent('Data as of 1 Aug 2026.');
  });

  it('neutral delta is not coloured as good or bad', () => {
    renderWithProviders(<HeadlineFigure label="X" value="1" delta={{ text: '2', direction: 'up', goodWhen: 'neutral' }} />);
    expect(screen.getByText('▲ 2')).toBeInTheDocument();
  });
});

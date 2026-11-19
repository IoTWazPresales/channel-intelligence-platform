import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import type { StoreMapStore } from '../types';
import { ProposedPinsPanel } from './ProposedPinsPanel';

function store(label: string, over: Partial<NonNullable<StoreMapStore['location_suggestion']>> = {}, customerId = 1): StoreMapStore {
  return {
    customer_id: customerId,
    customer_name: customerId === 1 ? 'Chain A' : 'Chain B',
    site_label: label,
    place_name: null,
    latitude: null,
    longitude: null,
    pinned: false,
    last_week_units: 1,
    stock_on_hand: 1,
    weeks_of_cover: 1,
    sell_through: 0.5,
    lines: [],
    location_suggestion: {
      outcome: 'suggest', reason: 'match', place: 'Examplevale', latitude: -30.5, longitude: 25.25,
      licence: 'GeoNames CC BY 4.0', method: 'contained', confidence: 0.85, matched_text: 'examplevale',
      ambiguous: false, alternatives: [], ...over,
    },
  };
}

function renderPanel(stores: StoreMapStore[], props: Partial<React.ComponentProps<typeof ProposedPinsPanel>> = {}) {
  const onConfirm = vi.fn();
  const onSkip = vi.fn();
  renderWithProviders(
    <ProposedPinsPanel stores={stores} saving={false} errors={{}} onConfirm={onConfirm} onSkip={onSkip} {...props} />,
  );
  return { onConfirm, onSkip };
}

describe('ProposedPinsPanel', () => {
  it('lists each proposal with store, customer, place, confidence and method, and says nothing is saved yet', () => {
    renderPanel([store('Chain A Examplevale Mall'), store('Chain B Otherton', { place: 'Otherton', method: 'fuzzy', confidence: 0.5 }, 2)]);
    const panel = screen.getByTestId('proposed-pins');
    expect(panel).toHaveTextContent('Proposed pins');
    expect(panel).toHaveTextContent('2');
    expect(panel).toHaveTextContent(/nothing is saved until you confirm/i);
    const rows = screen.getAllByTestId('proposed-pin-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Chain A Examplevale Mall');
    expect(rows[0]).toHaveTextContent('Chain A');
    expect(rows[0]).toHaveTextContent('Examplevale');
    expect(rows[0]).toHaveTextContent('High · 85%');
    expect(rows[0]).toHaveTextContent('Name inside label');
    expect(rows[1]).toHaveTextContent('Low · 50%');
    expect(rows[1]).toHaveTextContent('Close spelling');
  });

  it('shows nothing when there are no proposals', () => {
    renderPanel([]);
    expect(screen.getByTestId('proposed-pins')).toHaveTextContent('No proposed pins');
    expect(screen.queryAllByTestId('proposed-pin-row')).toHaveLength(0);
  });

  it('Confirm sends the proposal with no coordinates', () => {
    const { onConfirm } = renderPanel([store('S1')]);
    fireEvent.click(screen.getByTestId('proposal-confirm'));
    expect(onConfirm).toHaveBeenCalledWith([{ customer_id: 1, site_label: 'S1' }]);
  });

  it('Edit opens the coordinates, and Save sends the edited pin', () => {
    const { onConfirm } = renderPanel([store('S1')]);
    fireEvent.click(screen.getByTestId('proposal-edit'));
    const lat = within(screen.getByTestId('proposal-lat')).getByRole('textbox');
    const lon = within(screen.getByTestId('proposal-lon')).getByRole('textbox');
    expect(lat).toHaveValue('-30.5');
    expect(lon).toHaveValue('25.25');
    fireEvent.change(lat, { target: { value: '-26.1' } });
    fireEvent.change(lon, { target: { value: '28.2' } });
    fireEvent.click(screen.getByTestId('proposal-save'));
    expect(onConfirm).toHaveBeenCalledWith([{ customer_id: 1, site_label: 'S1', latitude: -26.1, longitude: 28.2 }]);
  });

  it('refuses an edit that is not a coordinate pair and sends nothing', () => {
    const { onConfirm } = renderPanel([store('S1')]);
    fireEvent.click(screen.getByTestId('proposal-edit'));
    fireEvent.change(within(screen.getByTestId('proposal-lat')).getByRole('textbox'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByTestId('proposal-save'));
    expect(screen.getByTestId('proposal-edit-error')).toHaveTextContent(/latitude/i);
    fireEvent.change(within(screen.getByTestId('proposal-lat')).getByRole('textbox'), { target: { value: '95' } });
    fireEvent.click(screen.getByTestId('proposal-save'));
    expect(screen.getByTestId('proposal-edit-error')).toHaveTextContent(/-90 and 90/);
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('proposal-cancel'));
    expect(screen.queryByTestId('proposal-save')).toBeNull();
  });

  it('Skip hands the store back without saving', () => {
    const stores = [store('S1')];
    const { onSkip, onConfirm } = renderPanel(stores);
    fireEvent.click(screen.getByTestId('proposal-skip'));
    expect(onSkip).toHaveBeenCalledWith(stores[0]);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('an ambiguous proposal lists the other places and confirms the one the steward picks', () => {
    const ambiguous = store('S1', {
      ambiguous: true, confidence: 0.54,
      alternatives: [{ place: 'Examplevale', latitude: -29.1, longitude: 26.6 }],
    });
    const { onConfirm } = renderPanel([ambiguous]);
    const row = screen.getByTestId('proposed-pin-row');
    expect(row).toHaveTextContent(/more than one place/i);
    fireEvent.click(screen.getByTestId('proposal-alternative'));
    fireEvent.click(screen.getByTestId('proposal-confirm'));
    expect(onConfirm).toHaveBeenCalledWith([{ customer_id: 1, site_label: 'S1', latitude: -29.1, longitude: 26.6 }]);
  });

  it('selects rows and confirms the selected ones in one request', () => {
    const { onConfirm } = renderPanel([store('A'), store('B', { confidence: 0.6 }), store('C', { confidence: 0.9 })]);
    expect(screen.getByTestId('proposal-confirm-selected')).toBeDisabled();
    const boxes = screen.getAllByTestId('proposal-select');
    fireEvent.click(within(boxes[0]).getByRole('checkbox'));
    fireEvent.click(within(boxes[2]).getByRole('checkbox'));
    expect(screen.getByTestId('proposal-confirm-selected')).toHaveTextContent('Confirm selected (2)');
    fireEvent.click(screen.getByTestId('proposal-confirm-selected'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0]).toEqual([
      { customer_id: 1, site_label: 'A' },
      { customer_id: 1, site_label: 'C' },
    ]);
  });

  it('"Select high confidence" ticks only high-confidence single-place proposals', () => {
    const ambiguous = store('AMB', { confidence: 0.54, ambiguous: true });
    renderPanel([store('A', { confidence: 0.95 }), store('B', { confidence: 0.6 }), ambiguous]);
    fireEvent.click(screen.getByTestId('proposal-select-high'));
    expect(screen.getByTestId('proposal-confirm-selected')).toHaveTextContent('Confirm selected (1)');
  });

  it('shows a row error beside that row and disables the buttons while saving', () => {
    const stores = [store('S1'), store('S2')];
    renderPanel(stores, { errors: { '1:S2': 'No proposal for this store; send coordinates' }, saving: true });
    const rows = screen.getAllByTestId('proposed-pin-row');
    expect(within(rows[1]).getByTestId('proposal-error')).toHaveTextContent('No proposal');
    expect(within(rows[0]).queryByTestId('proposal-error')).toBeNull();
    for (const button of screen.getAllByTestId('proposal-confirm')) expect(button).toBeDisabled();
    expect(screen.getByTestId('proposal-confirm-selected')).toBeDisabled();
  });

  it('wraps for a 390px screen: actions wrap and long labels break', () => {
    renderPanel([store('A very long store label that would otherwise push the row wider than a phone screen allows')]);
    const row = screen.getByTestId('proposed-pin-row');
    expect(getComputedStyle(within(row).getByTestId('proposal-actions')).flexWrap).toBe('wrap');
    expect(getComputedStyle(within(row).getByTestId('proposal-label')).overflowWrap).toBe('anywhere');
    expect(getComputedStyle(screen.getByTestId('proposed-pins-scroll')).overflowY).toBe('auto');
  });
});

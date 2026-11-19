import { describe, expect, it } from 'vitest';

import type { StoreMapStore } from '../types';
import {
  confidenceBand,
  confirmItemFor,
  methodLabel,
  proposalKey,
  proposedStores,
  selectableHighConfidence,
} from './pinProposals';

function store(over: Partial<StoreMapStore> & { label: string; confidence?: number | null; place?: string }): StoreMapStore {
  const { label, confidence = 0.9, place = 'Examplevale', ...rest } = over;
  return {
    customer_id: 1,
    customer_name: 'Chain A',
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
      outcome: 'suggest', reason: 'match', place, latitude: -30, longitude: 25,
      licence: 'GeoNames CC BY 4.0', method: 'contained', confidence, ambiguous: false, alternatives: [],
    },
    ...rest,
  };
}

describe('pinProposals', () => {
  it('lists only unpinned stores that have a proposal, highest confidence first', () => {
    const stores = [
      store({ label: 'low', confidence: 0.45 }),
      store({ label: 'high', confidence: 0.95 }),
      store({ label: 'pinned', pinned: true, latitude: 1, longitude: 2 }),
      store({ label: 'manual', location_suggestion: {
        outcome: 'manual', reason: 'none', place: null, latitude: null, longitude: null, licence: 'x',
      } }),
      store({ label: 'none', location_suggestion: null }),
      store({ label: 'mid', confidence: 0.7 }),
    ];
    expect(proposedStores(stores, new Set()).map((s) => s.site_label)).toEqual(['high', 'mid', 'low']);
  });

  it('leaves out skipped stores', () => {
    const stores = [store({ label: 'a' }), store({ label: 'b' })];
    const skipped = new Set([proposalKey(stores[0])]);
    expect(proposedStores(stores, skipped).map((s) => s.site_label)).toEqual(['b']);
  });

  it('keys one proposal per customer and store label', () => {
    expect(proposalKey(store({ label: 'a' }))).not.toBe(proposalKey(store({ label: 'a', customer_id: 2 })));
  });

  it('bands confidence', () => {
    expect(confidenceBand(0.95)).toBe('High');
    expect(confidenceBand(0.8)).toBe('High');
    expect(confidenceBand(0.7)).toBe('Medium');
    expect(confidenceBand(0.4)).toBe('Low');
    expect(confidenceBand(null)).toBe('Unknown');
  });

  it('names the method in words', () => {
    expect(methodLabel('exact')).toBe('Exact name');
    expect(methodLabel('contained')).toBe('Name inside label');
    expect(methodLabel('fuzzy')).toBe('Close spelling');
    expect(methodLabel(undefined)).toBe('');
  });

  it('confirms the proposal with no coordinates, and an edit with both', () => {
    const one = store({ label: 'a' });
    expect(confirmItemFor(one)).toEqual({ customer_id: 1, site_label: 'a' });
    expect(confirmItemFor(one, { latitude: -26.2, longitude: 28.1 })).toEqual({
      customer_id: 1, site_label: 'a', latitude: -26.2, longitude: 28.1,
    });
  });

  it('selects high-confidence, unambiguous proposals only', () => {
    const ambiguous = store({ label: 'amb', confidence: 0.5 });
    ambiguous.location_suggestion!.ambiguous = true;
    const stores = [store({ label: 'a', confidence: 0.9 }), store({ label: 'b', confidence: 0.6 }), ambiguous];
    expect(selectableHighConfidence(stores).map((s) => s.site_label)).toEqual(['a']);
  });
});

import { describe, expect, it } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';

import { EMPTY_CLICKS, clickReducer, effectiveSelection } from './clickFilters';
import { requestFor } from './requestFor';

describe('click selections narrow the dashboard bar', () => {
  it('intersects same-key selections, including ids represented as strings', () => {
    const clicks = clickReducer(EMPTY_CLICKS, { type: 'select', datum: { breakdown: 'customer', value: '101', label: 'Kestrel' } });
    expect(effectiveSelection({ customer: [101, 102] }, clicks)).toEqual({ customer: [101] });
  });

  it('preserves an empty intersection and prevents an unfiltered request', () => {
    const clicks = clickReducer(EMPTY_CLICKS, { type: 'select', datum: { breakdown: 'customer', value: 102, label: 'Marula' } });
    const filters = effectiveSelection({ customer: [101] }, clicks);
    expect(filters).toEqual({ customer: [] });
    expect(requestFor({ v: 1, query: { measures: ['dsi_sellout.units'] } }, { catalog, filters, window: null }))
      .toMatchObject({ status: 'blocked', reason: 'empty_intersection' });
  });

  it('keeps an impossible selection impossible when an additional chip is applied', () => {
    const clicks = clickReducer(EMPTY_CLICKS, { type: 'select', datum: { breakdown: 'region', value: 3, label: 'North' } });
    expect(effectiveSelection({ customer: [], region: [3] }, clicks)).toEqual({ customer: [], region: [3] });
  });

  it('restores the bar selection after clearing chips', () => {
    const clicks = clickReducer(EMPTY_CLICKS, { type: 'select', datum: { breakdown: 'customer', value: 102, label: 'Marula' } });
    expect(effectiveSelection({ customer: [101] }, clickReducer(clicks, { type: 'clear' }))).toEqual({ customer: [101] });
  });
});

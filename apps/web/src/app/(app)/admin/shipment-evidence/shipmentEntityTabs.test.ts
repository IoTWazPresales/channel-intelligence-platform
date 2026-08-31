import { describe, expect, it } from 'vitest';

import {
  defaultShipmentStewardFiltersForTab,
  shipmentStewardFiltersAfterTabSwitch,
  shipmentStewardFiltersMatchTabDefault,
} from './shipmentEntityTabs';
import { defaultShipmentStewardCandidateFilterState } from './shipmentStewardCandidateFilterLogic';

describe('shipmentEntityTabs S2 — tab switch resets chip filters', () => {
  it('returns tab-default filters for distributor and customer tabs', () => {
    expect(shipmentStewardFiltersAfterTabSwitch('distributor')).toEqual(
      defaultShipmentStewardFiltersForTab('distributor')
    );
    expect(shipmentStewardFiltersAfterTabSwitch('customer')).toEqual(
      defaultShipmentStewardFiltersForTab('customer')
    );
  });

  it('drops non-default queue/party state when switching tabs (parity with CPOR/CST)', () => {
    const dirty = {
      ...defaultShipmentStewardCandidateFilterState(),
      entity: 'distributor' as const,
      party: 'bill_to' as const,
      queue: 'needs_review' as const,
      verifyNameOnly: true,
    };
    expect(shipmentStewardFiltersMatchTabDefault(dirty, 'distributor')).toBe(false);

    const reset = shipmentStewardFiltersAfterTabSwitch('customer');
    expect(shipmentStewardFiltersMatchTabDefault(reset, 'customer')).toBe(true);
    expect(reset.party).toBe('all');
    expect(reset.queue).toBe('all');
    expect(reset.verifyNameOnly).toBe(false);
  });
});

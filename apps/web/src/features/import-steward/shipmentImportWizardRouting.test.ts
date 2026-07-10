import { describe, expect, it } from 'vitest';

import {
  shipmentJobHasValidationComplete,
  shipmentPipelineInFlight,
  shipmentWizardActiveStepFromServer,
} from './shipmentImportWizardRouting';
import { filterShipmentStewardCandidates } from './shipmentStewardCandidateFilterLogic';

describe('shipmentImportWizardRouting', () => {
  it('maps loaded to apply step', () => {
    expect(shipmentWizardActiveStepFromServer({ stage: 'loaded', status: 'completed' })).toBe(6);
  });

  it('maps running validate to validate step even when stage is validated', () => {
    expect(shipmentWizardActiveStepFromServer({ stage: 'validated', status: 'running' })).toBe(5);
    expect(shipmentPipelineInFlight({ stage: 'validated', status: 'running' })).toBe(true);
    expect(shipmentJobHasValidationComplete({ stage: 'validated', status: 'running' })).toBe(false);
  });

  it('maps shipment_mapping_ready to column mapping step', () => {
    expect(shipmentWizardActiveStepFromServer({ stage: 'shipment_mapping_ready', status: 'completed' })).toBe(4);
  });

  it('maps validated idle to validate & resolve step', () => {
    expect(shipmentWizardActiveStepFromServer({ stage: 'validated', status: 'completed' })).toBe(5);
  });
});

describe('filterShipmentStewardCandidates', () => {
  const plan = new Map<number, Record<string, unknown>>();

  it('keeps shipment_distributor rows when distributor tab filter is active', () => {
    const rows = [
      {
        id: 1,
        entity_type: 'shipment_distributor',
        status: 'needs_review',
        match_reason: null,
        context: { party: 'bill_to' },
        suggested_action: null,
      },
    ];
    const filtered = filterShipmentStewardCandidates(rows, { ...defaultFilters(), entity: 'distributor' }, plan);
    expect(filtered).toHaveLength(1);
  });

  it('filters out customer rows on distributor tab', () => {
    const rows = [
      {
        id: 2,
        entity_type: 'shipment_customer_token',
        status: 'needs_review',
        match_reason: null,
        context: {},
        suggested_action: null,
      },
    ];
    const filtered = filterShipmentStewardCandidates(rows, { ...defaultFilters(), entity: 'distributor' }, plan);
    expect(filtered).toHaveLength(0);
  });
});

function defaultFilters() {
  return {
    queue: 'all' as const,
    entity: 'all' as const,
    party: 'all' as const,
    verifyNameOnly: false,
    specialCategoryOnly: false,
    duplicateUnresolvedOnly: false,
  };
}

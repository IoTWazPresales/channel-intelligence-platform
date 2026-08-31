import { describe, expect, it } from 'vitest';

import type { ShipmentMappingCandidateRow } from './shipmentMappingCandidateDisplay';
import { filterShipmentStewardRowsBySearch } from './shipmentStewardListSearch';

function row(p: Partial<ShipmentMappingCandidateRow> & Pick<ShipmentMappingCandidateRow, 'id'>): ShipmentMappingCandidateRow {
  return {
    import_job_id: 1,
    entity_type: 'customer_dealer_token',
    normalized_key: 'acme',
    row_count: 1,
    status: 'needs_review',
    match_reason: null,
    confidence_score: null,
    sample_raw_values: ['ACME'],
    suggested_action: null,
    suggested_entity_id: null,
    suggested_distributor_code: null,
    suggested_distributor_name: null,
    suggested_customer_code: null,
    suggested_customer_name: null,
    context: null,
    ...p,
  };
}

describe('shipmentStewardListSearch S3 — debounced list search filter', () => {
  const rows = [
    row({ id: 1, normalized_key: 'ecole du centre', suggested_customer_name: 'Ecole Du Centre' }),
    row({ id: 2, normalized_key: 'widget-x', sample_raw_values: ['WIDGET-X'] }),
  ];

  it('returns all rows when search is empty or whitespace', () => {
    expect(filterShipmentStewardRowsBySearch(rows, '')).toEqual(rows);
    expect(filterShipmentStewardRowsBySearch(rows, '   ')).toEqual(rows);
  });

  it('filters by token, key, and suggested names (case-insensitive)', () => {
    expect(filterShipmentStewardRowsBySearch(rows, 'ecole').map((r) => r.id)).toEqual([1]);
    expect(filterShipmentStewardRowsBySearch(rows, 'WIDGET').map((r) => r.id)).toEqual([2]);
    expect(filterShipmentStewardRowsBySearch(rows, 'no-hit').map((r) => r.id)).toEqual([]);
  });
});

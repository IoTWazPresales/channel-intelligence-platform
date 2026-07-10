import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  defaultDsiStewardCandidateFilterState,
  filterDsiStewardCandidates,
  type DsiStewardCandidateFilterState,
} from './dsiStewardCandidateFilterLogic';

import {
  SHIPMENT_ENTITY_DIST,
  SHIPMENT_ENTITY_CUST,
} from './shipmentMappingCandidateDisplay';

/** @deprecated Prefer SHIPMENT_ENTITY_DIST from shipmentMappingCandidateDisplay */
export const SHIPMENT_ENTITY_DISTRIBUTOR = SHIPMENT_ENTITY_DIST;
/** @deprecated Prefer SHIPMENT_ENTITY_CUST from shipmentMappingCandidateDisplay */
export const SHIPMENT_ENTITY_CUSTOMER = SHIPMENT_ENTITY_CUST;

export type ShipmentStewardEntityFilter = 'all' | 'customer' | 'distributor';

export type ShipmentStewardCandidateFilterState = DsiStewardCandidateFilterState;

export const defaultShipmentStewardCandidateFilterState = defaultDsiStewardCandidateFilterState;

/** Map shipment tab entity filter to API / server list param (same strings as DSI tab filters). */
export function shipmentTabEntityFilter(tabId: 'distributor' | 'customer'): ShipmentStewardEntityFilter {
  return tabId === 'customer' ? 'customer' : 'distributor';
}

function toShipmentFilterSlice(
  row: DsiCandidateRow,
  planRow: Record<string, unknown> | undefined
): DsiCandidateRow {
  const entityType = (row.entity_type || '').trim();
  if (entityType === SHIPMENT_ENTITY_DIST || entityType === 'distributor_token') {
    return { ...row, entity_type: 'distributor_token' };
  }
  if (entityType === SHIPMENT_ENTITY_CUST || entityType === 'customer_dealer_token') {
    return { ...row, entity_type: 'customer_dealer_token' };
  }
  return row;
}

/**
 * Client-side steward filters for shipment candidates.
 * Normalizes shipment entity types so shared DSI queue/party/toggle logic applies.
 */
export function filterShipmentStewardCandidates(
  rows: DsiCandidateRow[],
  filters: ShipmentStewardCandidateFilterState,
  planByCandidateId: Map<number, Record<string, unknown>>
): DsiCandidateRow[] {
  const normalized = rows.map((row) => toShipmentFilterSlice(row, planByCandidateId.get(row.id)));
  return filterDsiStewardCandidates(normalized, filters, planByCandidateId);
}

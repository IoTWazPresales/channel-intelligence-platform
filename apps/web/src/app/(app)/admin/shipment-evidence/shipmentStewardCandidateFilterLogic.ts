import {
  defaultDsiStewardCandidateFilterState,
  filterDsiStewardCandidates,
  type DsiStewardCandidateFilterState,
} from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import type { DsiCandidateRow } from '@/features/import-steward/dsi-mapping-steward-panel';

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

/** Minimal row shape for client-side steward filters (shipment or DSI-shaped). */
export type ShipmentFilterableCandidate = {
  id: number;
  entity_type: string;
  status?: string | null;
  match_reason?: string | null;
  context?: Record<string, unknown> | null;
  suggested_action?: string | null;
};

function toShipmentFilterSlice(
  row: ShipmentFilterableCandidate,
  _planRow: Record<string, unknown> | undefined
): DsiCandidateRow {
  const entityType = (row.entity_type || '').trim();
  const asDsi = row as unknown as DsiCandidateRow;
  if (entityType === SHIPMENT_ENTITY_DIST || entityType === 'distributor_token') {
    return { ...asDsi, entity_type: 'distributor_token' };
  }
  if (entityType === SHIPMENT_ENTITY_CUST || entityType === 'customer_dealer_token') {
    return { ...asDsi, entity_type: 'customer_dealer_token' };
  }
  return asDsi;
}

/**
 * Client-side steward filters for shipment candidates.
 * Normalizes shipment entity types so shared DSI queue/party/toggle logic applies.
 */
export function filterShipmentStewardCandidates<T extends ShipmentFilterableCandidate>(
  rows: T[],
  filters: ShipmentStewardCandidateFilterState,
  planByCandidateId: Map<number, Record<string, unknown>>
): T[] {
  const normalized = rows.map((row) => toShipmentFilterSlice(row, planByCandidateId.get(row.id)));
  return filterDsiStewardCandidates(normalized, filters, planByCandidateId) as unknown as T[];
}

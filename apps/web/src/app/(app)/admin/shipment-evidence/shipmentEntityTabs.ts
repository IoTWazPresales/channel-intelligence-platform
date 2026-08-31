import type { ShipmentStewardCandidateFilterState } from './shipmentStewardCandidateFilterLogic';
import { defaultShipmentStewardCandidateFilterState } from './shipmentStewardCandidateFilterLogic';

export const SHIPMENT_ENTITY_TAB_ORDER = ['distributor', 'customer'] as const;

export type ShipmentEntityTabId = (typeof SHIPMENT_ENTITY_TAB_ORDER)[number];

export type ShipmentEntityTabMeta = {
  id: ShipmentEntityTabId;
  label: string;
  entityFilter: 'distributor' | 'customer';
  testId: string;
};

export const SHIPMENT_ENTITY_TAB_DEFS: readonly ShipmentEntityTabMeta[] = [
  {
    id: 'distributor',
    label: 'Distributors',
    entityFilter: 'distributor',
    testId: 'shipment-tab-distributor',
  },
  {
    id: 'customer',
    label: 'Channel partners',
    entityFilter: 'customer',
    testId: 'shipment-tab-customer',
  },
] as const;

export function defaultShipmentStewardFiltersForTab(tabId: ShipmentEntityTabId): ShipmentStewardCandidateFilterState {
  const tab = SHIPMENT_ENTITY_TAB_DEFS.find((t) => t.id === tabId);
  return {
    ...defaultShipmentStewardCandidateFilterState(),
    entity: tab?.entityFilter ?? 'all',
    party: 'all',
  };
}

export function shipmentStewardFiltersMatchTabDefault(
  filters: ShipmentStewardCandidateFilterState,
  tabId: ShipmentEntityTabId
): boolean {
  const def = defaultShipmentStewardFiltersForTab(tabId);
  return (
    filters.queue === def.queue &&
    filters.entity === def.entity &&
    filters.party === def.party &&
    filters.verifyNameOnly === def.verifyNameOnly &&
    filters.specialCategoryOnly === def.specialCategoryOnly &&
    filters.duplicateUnresolvedOnly === def.duplicateUnresolvedOnly
  );
}

/** S2: tab switch resets chip filters to the tab default (CPOR/CST parity). */
export function shipmentStewardFiltersAfterTabSwitch(tabId: ShipmentEntityTabId): ShipmentStewardCandidateFilterState {
  return defaultShipmentStewardFiltersForTab(tabId);
}

export function formatShipmentEntityTabLabel(
  tab: Pick<ShipmentEntityTabMeta, 'label'>,
  total: number | null,
  needsWork: number | null
): string {
  const count = total == null ? '…' : String(total);
  const nw = needsWork != null && needsWork > 0 ? `, ${needsWork} needs work` : '';
  return `${tab.label} (${count}${nw})`;
}

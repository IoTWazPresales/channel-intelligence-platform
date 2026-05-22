import type { DsiStewardCandidateFilterState, DsiStewardEntityFilter } from './dsiStewardCandidateFilterLogic';
import { defaultDsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';

/** Tab order: Distributors → Customers → Products → Region & channel (catalog tokens). */
export const DSI_ENTITY_TAB_ORDER = ['distributor', 'customer', 'product', 'region_channel'] as const;

export type DsiEntityTabId = (typeof DSI_ENTITY_TAB_ORDER)[number];

export type DsiEntityTabKind = 'entity_candidates' | 'catalog_geo';

export type DsiEntityTabMeta = {
  id: DsiEntityTabId;
  label: string;
  kind: DsiEntityTabKind;
  entityFilter: DsiStewardEntityFilter;
  testId: string;
};

export const DSI_ENTITY_TABS: readonly DsiEntityTabMeta[] = [
  {
    id: 'distributor',
    label: 'Distributors',
    kind: 'entity_candidates',
    entityFilter: 'distributor',
    testId: 'dsi-tab-distributor',
  },
  {
    id: 'customer',
    label: 'Customers',
    kind: 'entity_candidates',
    entityFilter: 'customer',
    testId: 'dsi-tab-customer',
  },
  {
    id: 'product',
    label: 'Products',
    kind: 'entity_candidates',
    entityFilter: 'product',
    testId: 'dsi-tab-product',
  },
  {
    id: 'region_channel',
    label: 'Region & channel',
    kind: 'catalog_geo',
    entityFilter: 'all',
    testId: 'dsi-tab-region-channel',
  },
] as const;

export const DSI_ENTITY_CANDIDATE_TABS = DSI_ENTITY_TABS.filter((t) => t.kind === 'entity_candidates');

export function isDsiEntityCandidateTab(tabId: DsiEntityTabId): boolean {
  return DSI_ENTITY_TABS.find((t) => t.id === tabId)?.kind === 'entity_candidates';
}

export function defaultDsiStewardFiltersForTab(tabId: DsiEntityTabId): DsiStewardCandidateFilterState {
  const tab = DSI_ENTITY_TABS.find((t) => t.id === tabId);
  return {
    ...defaultDsiStewardCandidateFilterState(),
    entity: tab?.entityFilter ?? 'all',
    party: tabId === 'distributor' ? 'all' : 'all',
  };
}

export function formatDsiEntityTabLabel(
  tab: DsiEntityTabMeta,
  total: number | null,
  needsWork: number | null
): string {
  const totalPart = total == null ? tab.label : `${tab.label} (${total})`;
  if (needsWork == null || needsWork <= 0) return totalPart;
  const workLabel = needsWork === 1 ? '1 needs work' : `${needsWork} needs work`;
  return `${totalPart} · ${workLabel}`;
}

export function dsiTabDependencyNudge(
  activeTab: DsiEntityTabId,
  openByTab: Record<DsiEntityTabId, number>,
  unresolvedGeoCount?: number
): string | null {
  if (activeTab === 'region_channel') {
    return 'Map file region and channel text to catalog rows (alias or create). Then re-run import validation so customer resolution picks up the new mappings.';
  }
  if (
    activeTab === 'customer' &&
    (unresolvedGeoCount ?? 0) > 0 &&
    (openByTab.region_channel ?? 0) > 0
  ) {
    const n = openByTab.region_channel ?? unresolvedGeoCount ?? 0;
    return `${n} unresolved region or channel value${n === 1 ? '' : 's'} from the file — use the Region & channel tab before bulk customer work when those columns are in the upload.`;
  }
  if (activeTab === 'customer' && (openByTab.distributor ?? 0) > 0) {
    const n = openByTab.distributor;
    return `${n} open distributor token${n === 1 ? '' : 's'} still need resolution. Resolving distributors first often clears downstream customer and product blockers.`;
  }
  if (activeTab === 'product') {
    const dist = openByTab.distributor ?? 0;
    const cust = openByTab.customer ?? 0;
    if (dist > 0 && cust > 0) {
      return `${dist} open distributor and ${cust} open customer token${cust === 1 ? '' : 's'} remain. Consider finishing upstream entities before product identifiers.`;
    }
    if (dist > 0) {
      return `${dist} open distributor token${dist === 1 ? '' : 's'} still need resolution before product work.`;
    }
    if (cust > 0) {
      return `${cust} open customer token${cust === 1 ? '' : 's'} still need resolution before product work.`;
    }
  }
  return null;
}

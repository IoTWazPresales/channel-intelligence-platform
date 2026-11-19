import type { LocationSuggestion, PinConfirmItem, StoreMapStore } from '../types';

/** One proposal per customer and store label. */
export function proposalKey(store: Pick<StoreMapStore, 'customer_id' | 'site_label'>): string {
  return `${store.customer_id}:${store.site_label}`;
}

export function hasProposal(store: StoreMapStore): boolean {
  const suggestion = store.location_suggestion;
  return !store.pinned
    && suggestion?.outcome === 'suggest'
    && suggestion.latitude != null
    && suggestion.longitude != null;
}

function confidenceOf(store: StoreMapStore): number {
  return store.location_suggestion?.confidence ?? 0;
}

/** Unpinned stores with a proposal that the steward has not skipped, most confident first. */
export function proposedStores(stores: StoreMapStore[], skipped: ReadonlySet<string>): StoreMapStore[] {
  return stores
    .filter((store) => hasProposal(store) && !skipped.has(proposalKey(store)))
    .sort((a, b) => confidenceOf(b) - confidenceOf(a) || a.site_label.localeCompare(b.site_label));
}

export function confidenceBand(confidence: number | null | undefined): 'High' | 'Medium' | 'Low' | 'Unknown' {
  if (confidence == null || Number.isNaN(confidence)) return 'Unknown';
  if (confidence >= 0.8) return 'High';
  if (confidence >= 0.55) return 'Medium';
  return 'Low';
}

export function confidenceText(suggestion: LocationSuggestion | null | undefined): string {
  const value = suggestion?.confidence;
  if (value == null) return '—';
  return `${confidenceBand(value)} · ${Math.round(value * 100)}%`;
}

export function methodLabel(method: LocationSuggestion['method']): string {
  if (method === 'exact') return 'Exact name';
  if (method === 'contained') return 'Name inside label';
  if (method === 'fuzzy') return 'Close spelling';
  return '';
}

/** No coordinates confirms the proposal as the server computes it; coordinates are the steward's edit. */
export function confirmItemFor(
  store: Pick<StoreMapStore, 'customer_id' | 'site_label'>,
  edit?: { latitude: number; longitude: number },
): PinConfirmItem {
  const item: PinConfirmItem = { customer_id: store.customer_id, site_label: store.site_label };
  if (edit) {
    item.latitude = edit.latitude;
    item.longitude = edit.longitude;
  }
  return item;
}

/** The safe bulk selection: high confidence and a single place. Ambiguous names stay for a person to read. */
export function selectableHighConfidence(stores: StoreMapStore[]): StoreMapStore[] {
  return stores.filter(
    (store) => hasProposal(store)
      && !store.location_suggestion?.ambiguous
      && confidenceBand(store.location_suggestion?.confidence) === 'High',
  );
}

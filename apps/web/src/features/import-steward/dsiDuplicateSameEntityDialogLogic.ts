/** Pure helpers for unified same-entity duplicate steward dialog. */

export type DupDisplayNameSource = 'primary' | 'peer' | 'custom';

export type DuplicateSameEntitySuggestion = {
  customerId: number;
  source: 'plan' | 'historical' | 'primary' | 'peer';
  label: string;
};

export function normalizeDupCustomerId(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 1 ? n : null;
}

export function buildDuplicateSameEntitySuggestions(input: {
  planSuggestedTargetId?: unknown;
  historicalCustomerId?: unknown;
  primarySuggestedEntityId?: unknown;
  peerSuggestedEntityId?: unknown;
}): DuplicateSameEntitySuggestion[] {
  const out: DuplicateSameEntitySuggestion[] = [];
  const seen = new Set<number>();

  const push = (customerId: number, source: DuplicateSameEntitySuggestion['source'], label: string) => {
    if (seen.has(customerId)) return;
    seen.add(customerId);
    out.push({ customerId, source, label });
  };

  const planId = normalizeDupCustomerId(input.planSuggestedTargetId);
  if (planId != null) push(planId, 'plan', `Plan suggestion (customer ${planId})`);

  const histId = normalizeDupCustomerId(input.historicalCustomerId);
  if (histId != null) push(histId, 'historical', `Previously resolved (customer ${histId})`);

  const primaryId = normalizeDupCustomerId(input.primarySuggestedEntityId);
  if (primaryId != null) push(primaryId, 'primary', `Primary token suggestion (customer ${primaryId})`);

  const peerId = normalizeDupCustomerId(input.peerSuggestedEntityId);
  if (peerId != null) push(peerId, 'peer', `Peer token suggestion (customer ${peerId})`);

  return out;
}

export function defaultDupCreateExpanded(suggestions: DuplicateSameEntitySuggestion[]): boolean {
  return suggestions.length === 0;
}

export function defaultDupDisplayNameSource(
  suggestions: DuplicateSameEntitySuggestion[]
): DupDisplayNameSource {
  return suggestions.length === 0 ? 'primary' : 'custom';
}

export function dealerGroupAccountLabel(ctx: Record<string, unknown> | null | undefined): string {
  const raw = ctx?.dealer_group_account_raw;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : '';
}

export function tokenDisplayLabel(
  normalizedKey: string,
  sampleRawValues: string[] | null | undefined
): string {
  const samples = sampleRawValues ?? [];
  for (const s of samples) {
    if (typeof s === 'string' && s.trim()) return s.trim();
  }
  const nk = (normalizedKey || '').trim();
  return nk && nk !== '__blank__' ? nk : normalizedKey;
}

export function resolveDupDisplayName(
  source: DupDisplayNameSource,
  primaryTokenLabel: string,
  peerTokenLabel: string,
  dealerGroupAccount: string,
  customName: string
): string {
  if (source === 'custom') return customName.trim();
  if (dealerGroupAccount) return dealerGroupAccount;
  if (source === 'peer') return peerTokenLabel.trim();
  return primaryTokenLabel.trim();
}

export function isDupSameEntitySubmitDisabled(input: {
  peerKey: string;
  primaryNormalizedKey: string;
  pickCustomerId: number | '';
  dupCreateMode: boolean;
  dupDisplayName: string;
}): boolean {
  if (!input.peerKey.trim()) return true;
  if (input.peerKey.trim() === input.primaryNormalizedKey.trim()) return true;
  if (input.pickCustomerId !== '') return false;
  if (input.dupCreateMode && input.dupDisplayName.trim()) return false;
  return true;
}

export type DupSameEntitySubmitBody = {
  peer_normalized_key: string;
  customer_id?: number;
  display_name?: string;
  plan_suggested_target_id?: number;
  audit_note?: string;
};

export function buildDupSameEntitySubmitBody(input: {
  peerKey: string;
  pickCustomerId: number | '';
  dupCreateMode: boolean;
  dupDisplayName: string;
  planSuggestedTargetId?: unknown;
  auditNote: string;
}): DupSameEntitySubmitBody | null {
  const peer = input.peerKey.trim();
  if (!peer) return null;

  const body: DupSameEntitySubmitBody = {
    peer_normalized_key: peer,
    audit_note: input.auditNote.trim() || undefined,
  };

  const planId = normalizeDupCustomerId(input.planSuggestedTargetId);
  if (planId != null) body.plan_suggested_target_id = planId;

  if (input.pickCustomerId !== '') {
    body.customer_id = Number(input.pickCustomerId);
    return body;
  }

  if (input.dupCreateMode && input.dupDisplayName.trim()) {
    body.display_name = input.dupDisplayName.trim();
    return body;
  }

  return null;
}

export function firstSuggestionCustomerId(
  suggestions: DuplicateSameEntitySuggestion[]
): number | '' {
  const first = suggestions[0];
  return first ? first.customerId : '';
}

export type DupClusterSameEntitySubmitBody = {
  customer_id?: number;
  display_name?: string;
  plan_suggested_target_id?: number;
  audit_note?: string;
};

export function isDupClusterSameEntitySubmitDisabled(input: {
  pickCustomerId: number | '';
  dupCreateMode: boolean;
  dupDisplayName: string;
}): boolean {
  if (input.pickCustomerId !== '') return false;
  if (input.dupCreateMode && input.dupDisplayName.trim()) return false;
  return true;
}

export function buildDupClusterSameEntitySubmitBody(input: {
  pickCustomerId: number | '';
  dupCreateMode: boolean;
  dupDisplayName: string;
  planSuggestedTargetId?: unknown;
  auditNote: string;
}): DupClusterSameEntitySubmitBody | null {
  const body: DupClusterSameEntitySubmitBody = {
    audit_note: input.auditNote.trim() || undefined,
  };

  const planId = normalizeDupCustomerId(input.planSuggestedTargetId);
  if (planId != null) body.plan_suggested_target_id = planId;

  if (input.pickCustomerId !== '') {
    body.customer_id = Number(input.pickCustomerId);
    return body;
  }

  if (input.dupCreateMode && input.dupDisplayName.trim()) {
    body.display_name = input.dupDisplayName.trim();
    return body;
  }

  return null;
}

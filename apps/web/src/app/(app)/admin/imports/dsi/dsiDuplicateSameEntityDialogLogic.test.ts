import { describe, expect, it } from 'vitest';

import {
  buildDuplicateSameEntitySuggestions,
  buildDupClusterSameEntitySubmitBody,
  buildDupSameEntitySubmitBody,
  defaultDupCreateExpanded,
  firstSuggestionCustomerId,
  isDupSameEntitySubmitDisabled,
  resolveDupDisplayName,
} from './dsiDuplicateSameEntityDialogLogic';

describe('buildDuplicateSameEntitySuggestions', () => {
  it('orders plan, historical, primary, peer without duplicates', () => {
    const s = buildDuplicateSameEntitySuggestions({
      planSuggestedTargetId: 10,
      historicalCustomerId: 10,
      primarySuggestedEntityId: 20,
      peerSuggestedEntityId: 30,
    });
    expect(s.map((x) => x.customerId)).toEqual([10, 20, 30]);
    expect(s[0]?.source).toBe('plan');
  });
});

describe('defaultDupCreateExpanded', () => {
  it('expands create when no suggestions', () => {
    expect(defaultDupCreateExpanded([])).toBe(true);
    expect(defaultDupCreateExpanded([{ customerId: 1, source: 'plan', label: 'x' }])).toBe(false);
  });
});

describe('firstSuggestionCustomerId', () => {
  it('returns first suggestion id or empty', () => {
    expect(firstSuggestionCustomerId([])).toBe('');
    expect(
      firstSuggestionCustomerId([{ customerId: 42, source: 'plan', label: 'Plan' }])
    ).toBe(42);
  });
});

describe('isDupSameEntitySubmitDisabled', () => {
  it('disabled until customer selected or create name confirmed', () => {
    expect(
      isDupSameEntitySubmitDisabled({
        peerKey: 'peer',
        primaryNormalizedKey: 'primary',
        pickCustomerId: '',
        dupCreateMode: false,
        dupDisplayName: '',
      })
    ).toBe(true);
    expect(
      isDupSameEntitySubmitDisabled({
        peerKey: 'peer',
        primaryNormalizedKey: 'primary',
        pickCustomerId: 5,
        dupCreateMode: false,
        dupDisplayName: '',
      })
    ).toBe(false);
    expect(
      isDupSameEntitySubmitDisabled({
        peerKey: 'peer',
        primaryNormalizedKey: 'primary',
        pickCustomerId: '',
        dupCreateMode: true,
        dupDisplayName: 'Rectron',
      })
    ).toBe(false);
  });
});

describe('buildDupSameEntitySubmitBody', () => {
  it('sends customer_id when existing customer selected', () => {
    const body = buildDupSameEntitySubmitBody({
      peerKey: 'peer-a',
      pickCustomerId: 77,
      dupCreateMode: false,
      dupDisplayName: '',
      planSuggestedTargetId: 10,
      auditNote: 'note',
    });
    expect(body).toEqual({
      peer_normalized_key: 'peer-a',
      customer_id: 77,
      plan_suggested_target_id: 10,
      audit_note: 'note',
    });
  });

  it('sends display_name when create path confirmed', () => {
    const body = buildDupSameEntitySubmitBody({
      peerKey: 'peer-a',
      pickCustomerId: '',
      dupCreateMode: true,
      dupDisplayName: 'Rectron Cape Town',
      auditNote: '',
    });
    expect(body).toEqual({
      peer_normalized_key: 'peer-a',
      display_name: 'Rectron Cape Town',
    });
  });

  it('prefers customer_id over create when both set', () => {
    const body = buildDupSameEntitySubmitBody({
      peerKey: 'peer',
      pickCustomerId: 9,
      dupCreateMode: true,
      dupDisplayName: 'New Name',
      auditNote: '',
    });
    expect(body?.customer_id).toBe(9);
    expect(body?.display_name).toBeUndefined();
  });
});

describe('resolveDupDisplayName', () => {
  it('uses dealer group when not custom', () => {
    expect(
      resolveDupDisplayName('primary', 'rectron blm', 'rectron dbn', 'Rectron Group', '')
    ).toBe('Rectron Group');
  });
});

describe('buildDupClusterSameEntitySubmitBody', () => {
  it('builds cluster map with customer_id', () => {
    const body = buildDupClusterSameEntitySubmitBody({
      pickCustomerId: 227,
      dupCreateMode: false,
      dupDisplayName: '',
      auditNote: 'cluster',
    });
    expect(body).toEqual({ customer_id: 227, audit_note: 'cluster' });
  });
});

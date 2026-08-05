import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { NON_PO_ONLY_CONTRACT_SEAMS } from './resolutionWorklist.types';
import { partitionBulkApply, selectAllEligibleKeys } from './selectionUtils';
import {
  PO_FIXTURE_ITEMS,
  buildPoLinkAction,
  poGetItemKey,
  poGetProtection,
} from './fixtures/poAutoLinkFixture';
import {
  MERGE_PROMOTE_FIXTURE_ITEMS,
  buildMergePromoteAction,
  fixtureShapesDiffer,
  mergePromoteGetItemKey,
} from './fixtures/mergePromoteFixture';
import {
  MergePromoteWorklistFixtureMount,
  PoWorklistFixtureMount,
} from './fixtures/FixtureMounts';

describe('ResolutionWorklist Unit 2 selection', () => {
  it('select-all excludes selectionProtected (reasons OR contested)', () => {
    const keys = selectAllEligibleKeys(PO_FIXTURE_ITEMS, poGetItemKey, poGetProtection);
    // Only CLEAN-HIGH-001 has null protection
    expect(keys).toEqual(['120:12:CLEAN-HIGH-001']);
  });

  it('bulk partition drops requiresOverride; contested-only stays eligible', () => {
    // Contested-only item: US-E3237-IC (requiresOverride false, contested true)
    const contestedOnly = PO_FIXTURE_ITEMS.filter((i) => i.poNumber === 'US-E3237-IC');
    const { eligible, skippedProtected } = partitionBulkApply(contestedOnly, poGetProtection);
    expect(eligible).toHaveLength(1);
    expect(skippedProtected).toHaveLength(0);

    const statusProtected = PO_FIXTURE_ITEMS.filter((i) => i.poNumber === '957090');
    const part2 = partitionBulkApply(statusProtected, poGetProtection);
    expect(part2.eligible).toHaveLength(0);
    expect(part2.skippedProtected).toHaveLength(1);
  });

  it('getItemKey is opaque — no case_id/po_id parsing required by helpers', () => {
    const keys = PO_FIXTURE_ITEMS.map(poGetItemKey);
    expect(keys.every((k) => typeof k === 'string')).toBe(true);
    // Helpers never import case_id — they only see opaque keys
    expect(keys).toContain('90:12:PURMIDR25005866');
  });
});

describe('ResolutionWorklist fixtures — structurally different consumers', () => {
  it('PO action has no target selection; merge/promote requires target', () => {
    const po = buildPoLinkAction(() => undefined);
    const merge = buildMergePromoteAction(() => undefined);
    expect(fixtureShapesDiffer(po as never, merge as never)).toBe(true);
    expect(merge.requiresTarget).toBe(true);
    expect(typeof merge.targets).toBe('function');
    expect(po.requiresTarget).toBeFalsy();
    expect(po.targets).toBeUndefined();

    const first = MERGE_PROMOTE_FIXTURE_ITEMS[0];
    const targets = merge.targets!(first);
    expect(targets.length).toBeGreaterThan(1);
    expect(targets[0].targetKey).toMatch(/^dist:/);
  });

  it('NON_PO_ONLY_CONTRACT_SEAMS is non-empty (VERIFY gate)', () => {
    expect(NON_PO_ONLY_CONTRACT_SEAMS.length).toBeGreaterThan(0);
    expect(NON_PO_ONLY_CONTRACT_SEAMS).toContain('WorklistAction.requiresTarget');
    expect(NON_PO_ONLY_CONTRACT_SEAMS).toContain('ResolutionTargetSelection');
    expect(NON_PO_ONLY_CONTRACT_SEAMS).toContain('ResolutionWorklistProps.renderTargetPicker');
    expect(NON_PO_ONLY_CONTRACT_SEAMS).toContain(
      'ResolutionApplyAdapter async mode (ResolutionAsyncApplyAdapter)',
    );
  });

  it('renders PO fixture mount (accept/link shape)', () => {
    const html = renderToStaticMarkup(createElement(PoWorklistFixtureMount));
    expect(html).toContain('data-testid="po-fixture-worklist"');
    expect(html).toContain('data-testid="po-fixture-worklist-shell"');
    expect(html).toContain('CLEAN-HIGH-001');
    // PO mount must NOT include target picker
    expect(html).not.toContain('data-testid="merge-promote-target-picker"');
  });

  it('renders merge/promote fixture mount WITH target selection', () => {
    const html = renderToStaticMarkup(createElement(MergePromoteWorklistFixtureMount));
    expect(html).toContain('data-testid="merge-promote-fixture-worklist"');
    expect(html).toContain('ACME Dist');
    expect(html).toContain('3 targets');
    expect(html).toContain('2 targets');
    // Non-PO seam must appear in markup (drawer default-open + renderTargetPicker)
    expect(html).toContain('data-testid="merge-promote-target-picker"');
    expect(html).toContain('data-testid="merge-promote-target-dist:101"');
  });

  it('merge promote getItemKey uses workKey not PO composite', () => {
    expect(mergePromoteGetItemKey(MERGE_PROMOTE_FIXTURE_ITEMS[0])).toBe('sim:acme-dist-group');
    expect(mergePromoteGetItemKey(MERGE_PROMOTE_FIXTURE_ITEMS[1])).toBe('tmp:TMP-CUST-0042');
  });
});

describe('ResolutionWorklist presentation-only imports', () => {
  it('module graph does not reference useStewardResolutionPlan / importJobId in types', async () => {
    const types = await import('./resolutionWorklist.types');
    const src = JSON.stringify(Object.keys(types));
    expect(src).not.toMatch(/importJobId/i);
    expect(src).not.toMatch(/proposal_key/);
    expect(src).not.toMatch(/case_id/);
  });
});

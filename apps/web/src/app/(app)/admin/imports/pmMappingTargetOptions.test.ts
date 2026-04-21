import { describe, expect, it } from 'vitest';

import type { PmFieldDefinition } from './pmMappingHelpers';

import {
  buildTargetUsageMap,
  enrichPmMappingTargets,
  filterAndSortPmTargets,
  type EnrichedPmTargetOption,
} from './pmMappingTargetOptions';

const MOCK_DEFS: PmFieldDefinition[] = [
  {
    key: 'display_name',
    label: 'display_name',
    group: 'required_core',
    importance: 'critical',
    dim_persistence: 'canonical',
    role: 'commercial',
    description: '',
  },
  {
    key: 'technical_product_id',
    label: 'technical_product_id',
    group: 'required_core',
    importance: 'critical',
    dim_persistence: 'canonical',
    role: 'technical',
    description: '',
  },
  {
    key: 'market_sku',
    label: 'market_sku',
    group: 'commercial_identity',
    importance: 'high',
    dim_persistence: 'canonical',
    role: 'commercial',
    description: '',
  },
  {
    key: 'country_code',
    label: 'country_code',
    group: 'optional',
    importance: 'low',
    dim_persistence: 'canonical',
    role: 'classification',
    description: '',
  },
];

describe('pmMappingTargetOptions', () => {
  it('maps usage by target', () => {
    const u = buildTargetUsageMap([
      { header: 'ColA', target: 'display_name' },
      { header: 'ColB', target: 'market_sku' },
      { header: 'ColC', target: '' },
    ]);
    expect(u.display_name).toEqual(['ColA']);
    expect(u.market_sku).toEqual(['ColB']);
    expect(u.country_code).toBeUndefined();
  });

  it('prioritizes required targets that are still unmapped', () => {
    const usage = buildTargetUsageMap([{ header: 'X', target: '' }]);
    const enriched = enrichPmMappingTargets({
      defs: MOCK_DEFS,
      requiredFields: ['display_name'],
      identityTargets: ['technical_product_id'],
      usage,
      currentHeader: 'X',
    });
    const dn = enriched.find((e) => e.key === 'display_name');
    const cc = enriched.find((e) => e.key === 'country_code');
    expect(dn!.sortTier).toBeLessThan(cc!.sortTier);
  });

  it('demotes duplicate targets mapped by other columns', () => {
    const usage = buildTargetUsageMap([
      { header: 'Product', target: 'display_name' },
      { header: 'Desc', target: '' },
    ]);
    const enriched = enrichPmMappingTargets({
      defs: MOCK_DEFS,
      requiredFields: ['display_name'],
      identityTargets: ['technical_product_id'],
      usage,
      currentHeader: 'Desc',
    });
    const dup = enriched.find((e) => e.key === 'display_name');
    expect(dup!.duplicateFromHeaders).toContain('Product');
    expect(dup!.sortTier).toBeGreaterThan(50);
  });

  it('filterAndSortPmTargets boosts exact label matches within a tier bucket', () => {
    const usage = buildTargetUsageMap([]);
    const enriched = enrichPmMappingTargets({
      defs: MOCK_DEFS,
      requiredFields: [],
      identityTargets: [],
      usage,
      currentHeader: 'Any',
    });
    const sorted = filterAndSortPmTargets(enriched, {
      inputValue: 'country_code',
      getOptionLabel: (o: EnrichedPmTargetOption) => o.label,
    } as Parameters<typeof filterAndSortPmTargets>[1]);
    expect(sorted[0]?.key).toBe('country_code');
  });
});

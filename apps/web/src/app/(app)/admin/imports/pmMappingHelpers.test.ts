import { describe, expect, it } from 'vitest';

import {
  initPmColumnDrafts,
  applyPmDispositionDraft,
  applyPmTargetDraft,
  pmColumnsToDispositionDraft,
  pmColumnsToTargetDraft,
  pmDraftsToApiColumns,
} from './pmMappingHelpers';

describe('initPmColumnDrafts', () => {
  it('prefers saved mapping_decisions over suggestions', () => {
    const d = initPmColumnDrafts(
      ['A', 'B'],
      { A: { target: 'display_name' }, B: { target: 'technical_product_id' } },
      { A: { target: 'technical_product_id' }, B: { target: 'display_name' } }
    );
    expect(d.find((x) => x.header === 'A')?.target).toBe('technical_product_id');
    expect(d.find((x) => x.header === 'B')?.target).toBe('display_name');
  });

  it('pre-fills target for auto_map, suggest, and legacy suggestions without mapper_action', () => {
    const suggest = initPmColumnDrafts(['A'], { A: { target: 'display_name', mapper_action: 'suggest' } }, null);
    expect(suggest[0].target).toBe('display_name');
    expect(suggest[0].disposition).not.toBe('ignore');

    const auto = initPmColumnDrafts(['A'], { A: { target: 'technical_product_id', mapper_action: 'auto_map' } }, null);
    expect(auto[0].target).toBe('technical_product_id');
    expect(auto[0].disposition).not.toBe('ignore');

    const legacy = initPmColumnDrafts(['A'], { A: { target: 'display_name' } }, null);
    expect(legacy[0].target).toBe('display_name');
  });

  it('uses disposition when unmapped', () => {
    const d = initPmColumnDrafts(['X'], { X: { disposition: 'stage_raw' } }, null);
    expect(d[0].target).toBe('');
    expect(d[0].disposition).toBe('stage_raw');
  });
});

describe('pmDraftsToApiColumns', () => {
  it('sends target for mapped and disposition for unmapped', () => {
    const body = pmDraftsToApiColumns([
      { header: 'sku', target: 'sku', disposition: 'ignore' },
      { header: 'extra', target: '', disposition: 'attribute_candidate' },
    ]);
    expect(body).toEqual([
      { header: 'sku', target: 'sku', disposition: null },
      { header: 'extra', target: null, disposition: 'attribute_candidate' },
    ]);
  });
});

describe('pmColumns panel draft bridges', () => {
  it('round-trips target and disposition drafts', () => {
    const cols = [
      { header: 'A', target: 'display_name', disposition: 'ignore' as const },
      { header: 'B', target: '', disposition: 'stage_raw' as const },
    ];
    expect(pmColumnsToTargetDraft(cols)).toEqual({ A: 'display_name' });
    expect(pmColumnsToDispositionDraft(cols)).toEqual({ B: 'stage_raw' });

    const afterTarget = applyPmTargetDraft(cols, { B: 'technical_product_id' });
    expect(afterTarget.find((c) => c.header === 'B')?.target).toBe('technical_product_id');
    expect(afterTarget.find((c) => c.header === 'A')?.target).toBe('');

    const afterDisp = applyPmDispositionDraft(
      [{ header: 'B', target: '', disposition: 'ignore' as const }],
      { B: 'attribute_candidate' }
    );
    expect(afterDisp[0].disposition).toBe('attribute_candidate');
  });
});

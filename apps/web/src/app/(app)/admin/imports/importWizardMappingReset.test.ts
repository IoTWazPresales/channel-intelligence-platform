import { describe, expect, it } from 'vitest';

import { mappingDraftForJobChange, mappingStateMatchesJob } from './importWizardMappingReset';

describe('importWizardMappingReset', () => {
  it('clears draft when lastJobId changes after Back + re-upload', () => {
    expect(mappingDraftForJobChange(10, 11, { SKU: 'sku' })).toEqual({});
  });

  it('keeps draft when the same job is rebound', () => {
    const draft = { SKU: 'sku' };
    expect(mappingDraftForJobChange(10, 10, draft)).toBe(draft);
  });

  it('does not render mapping until mapping-state id matches the current job', () => {
    expect(mappingStateMatchesJob(10, 11)).toBe(false);
    expect(mappingStateMatchesJob(11, 11)).toBe(true);
    expect(mappingStateMatchesJob(undefined, 11)).toBe(false);
  });
});

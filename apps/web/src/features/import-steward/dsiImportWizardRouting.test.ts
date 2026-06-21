import { describe, expect, it } from 'vitest';

import {
  dsiJobHasValidationComplete,
  dsiWizardActiveStepFromServer,
} from './dsiImportWizardRouting';

describe('dsiJobHasValidationComplete', () => {
  it('is true for validated stage', () => {
    expect(dsiJobHasValidationComplete({ stage: 'validated', status: 'completed' })).toBe(true);
  });

  it('is true for completed_with_errors status even when stage lags', () => {
    expect(
      dsiJobHasValidationComplete({ stage: 'dsi_mapping_ready', status: 'completed_with_errors' })
    ).toBe(true);
  });

  it('is false before validate finishes', () => {
    expect(dsiJobHasValidationComplete({ stage: 'dsi_mapping_ready', status: 'pending' })).toBe(false);
  });
});

describe('dsiWizardActiveStepFromServer', () => {
  it('routes completed_with_errors jobs to validate/steward step', () => {
    expect(
      dsiWizardActiveStepFromServer({ stage: 'dsi_mapping_ready', status: 'completed_with_errors' })
    ).toBe(6);
  });

  it('keeps validate step while status is running before stage flips', () => {
    expect(dsiWizardActiveStepFromServer({ stage: 'dsi_mapping_ready', status: 'running' })).toBe(6);
  });

  it('routes mapping-ready idle jobs to column mapping step', () => {
    expect(dsiWizardActiveStepFromServer({ stage: 'dsi_mapping_ready', status: 'pending' })).toBe(5);
  });

  it('routes validated stage to steward step', () => {
    expect(dsiWizardActiveStepFromServer({ stage: 'validated', status: 'completed_with_errors' })).toBe(6);
  });

  it('routes loaded stage to apply step', () => {
    expect(dsiWizardActiveStepFromServer({ stage: 'loaded', status: 'completed' })).toBe(7);
  });
});

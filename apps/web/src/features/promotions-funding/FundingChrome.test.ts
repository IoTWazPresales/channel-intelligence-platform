import { describe, expect, it } from 'vitest';

import { fundingLensFromPath } from './FundingChrome';

describe('fundingLensFromPath', () => {
  it('maps production routes onto the lab lenses', () => {
    expect(fundingLensFromPath('/promotions')).toBe('planner');
    expect(fundingLensFromPath('/commercial-planner/cpor-cases')).toBe('book');
    expect(fundingLensFromPath('/commercial-planner/cpor-cases/12')).toBe('book');
    expect(fundingLensFromPath('/commercial-planner/cpor-cases/claims')).toBe('claims');
    expect(fundingLensFromPath('/commercial-planner/cpor-cases/payment-evidence-import')).toBe('payments');
    expect(fundingLensFromPath('/commercial-planner/cpor-cases/historical-import')).toBe('templates');
    expect(fundingLensFromPath('/admin/customer-commercial-terms')).toBe('pricing');
    expect(fundingLensFromPath('/budgets')).toBe('budgets');
  });
});

import { describe, expect, it } from 'vitest';

import { customerPrimaryName, customerSecondaryCode, SHOW_CUSTOMER_CODE } from './customerDisplay';

describe('customerDisplay', () => {
  it('shows the name as primary and does not weld the CIP-minted code into it', () => {
    expect(customerPrimaryName('Takealot', 'CUST-000012')).toBe('Takealot');
    expect(customerPrimaryName('Takealot', 'CUST-000012')).not.toContain('CUST-000012');
  });

  it('never surfaces the CIP-minted code in an identity position', () => {
    // Warren 2026-09-21: codes belong only in a dedicated "Customer code" column the user
    // adds. This assertion is the regression guard - do not relax it back to true.
    expect(SHOW_CUSTOMER_CODE).toBe(false);
    expect(customerSecondaryCode('CUST-000012')).toBeNull();
  });

  it('still falls back to the code when there is no name at all', () => {
    // A nameless row must render something addressable rather than an em dash.
    expect(customerPrimaryName(null, 'CUST-000012')).toBe('CUST-000012');
    expect(customerPrimaryName('  ', null)).toBe('—');
  });
});

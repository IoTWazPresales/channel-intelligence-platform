import { describe, expect, it } from 'vitest';

import { customerPrimaryName, customerSecondaryCode, SHOW_CUSTOMER_CODE } from './customerDisplay';

describe('customerDisplay', () => {
  it('shows the name as primary and does not weld the CIP-minted code into it', () => {
    expect(customerPrimaryName('Takealot', 'CUST-000012')).toBe('Takealot');
    expect(customerPrimaryName('Takealot', 'CUST-000012')).not.toContain('CUST-000012');
  });

  it('keeps the code in one subordinate helper that SHOW_CUSTOMER_CODE can hide', () => {
    expect(SHOW_CUSTOMER_CODE).toBe(true);
    expect(customerSecondaryCode('CUST-000012')).toBe('CUST-000012');
  });
});

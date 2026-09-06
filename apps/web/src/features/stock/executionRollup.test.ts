import { describe, expect, it } from 'vitest';

import { customersUnderPlanShare, rollCustomers } from './executionRollup';

describe('executionRollup', () => {
  it('sums plan and shipped by customer label', () => {
    const rows = rollCustomers([
      { customer_label: 'Acme', planned_units: 10, shipped_units: 4 },
      { customer_label: 'Acme', planned_units: 5, shipped_units: 5 },
      { customer_label: 'Beta', planned_units: 20, shipped_units: 20 },
    ]);
    expect(rows).toEqual([
      { customer: 'Beta', plan: 20, shipped: 20 },
      { customer: 'Acme', plan: 15, shipped: 9 },
    ]);
  });

  it('counts customers under 70% of plan and ignores zero-plan rows', () => {
    const rows = rollCustomers([
      { customer_label: 'Short', planned_units: 100, shipped_units: 69 },
      { customer_label: 'Ok', planned_units: 100, shipped_units: 70 },
      { customer_label: 'Zero', planned_units: 0, shipped_units: 5 },
    ]);
    expect(customersUnderPlanShare(rows)).toBe(1);
  });
});

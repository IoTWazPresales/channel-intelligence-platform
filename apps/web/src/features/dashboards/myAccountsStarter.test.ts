import { describe, expect, it } from 'vitest';

import { MY_ACCOUNTS_TEMPLATE, myAccountsStarterId } from './DashboardWorkspace';
import type { Dashboard } from './types';

const d = (id: number, template_key: string | null, owner_user_id: number | null) =>
  ({ id, template_key, owner_user_id }) as unknown as Dashboard;

describe('myAccountsStarterId (D-0141 starting screen)', () => {
  it('finds the caller\'s own My accounts starter, newest first as listed', () => {
    const items = [d(9, 'sellthrough_stock', 7), d(8, MY_ACCOUNTS_TEMPLATE, 3), d(6, MY_ACCOUNTS_TEMPLATE, 7), d(4, MY_ACCOUNTS_TEMPLATE, 7)];
    expect(myAccountsStarterId(items, '7')).toBe(6);
    expect(myAccountsStarterId(items, 3)).toBe(8);
  });

  it('ignores someone else\'s or a published starter, and an unknown user', () => {
    const items = [d(8, MY_ACCOUNTS_TEMPLATE, 3), d(5, MY_ACCOUNTS_TEMPLATE, null)];
    expect(myAccountsStarterId(items, '7')).toBeNull();
    expect(myAccountsStarterId(items, null)).toBeNull();
  });
});

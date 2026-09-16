import { describe, expect, it } from 'vitest';

import {
  filterTokensByExactCaseCode,
  isExactCaseCode,
  parseExactPaymentEvidenceCode,
} from './paymentEvidenceCode';

describe('paymentEvidenceCode', () => {
  it('trims the URL token and rejects empty', () => {
    expect(parseExactPaymentEvidenceCode('  C19A50693  ')).toBe('C19A50693');
    expect(parseExactPaymentEvidenceCode('')).toBeNull();
    expect(parseExactPaymentEvidenceCode('   ')).toBeNull();
    expect(parseExactPaymentEvidenceCode(null)).toBeNull();
  });

  it('matches exact Case ID only — no prefix, no case-fold', () => {
    expect(isExactCaseCode('C19A50693', 'C19A50693')).toBe(true);
    expect(isExactCaseCode('C19A50693X', 'C19A50693')).toBe(false);
    expect(isExactCaseCode('c19a50693', 'C19A50693')).toBe(false);
    expect(isExactCaseCode('C19A', 'C19A50693')).toBe(false);
  });

  it('filters steward tokens by exact token equality', () => {
    const items = [{ token: 'C19A50693' }, { token: 'C19A50693X' }, { token: 'HIST-CUST' }];
    expect(filterTokensByExactCaseCode(items, 'C19A50693')).toEqual([{ token: 'C19A50693' }]);
  });
});

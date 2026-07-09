import { describe, expect, it } from 'vitest';

import {
  shippingDistributorCellValue,
  shippingDistributorSearchHaystack,
} from './shippingDistributorDisplay';

describe('shippingDistributorDisplay', () => {
  it('shows human name for promoted distributor', () => {
    expect(
      shippingDistributorCellValue({
        distributor_display: 'Mustek Limited',
        distributor_name: 'Mustek Limited',
        distributor_code: 'DIST-MUSTEK',
        distributor_is_provisional: false,
      })
    ).toBe('Mustek Limited');
  });

  it('appends TMP code as secondary line when provisional', () => {
    expect(
      shippingDistributorCellValue({
        distributor_display: 'Acme Distributors',
        distributor_name: 'Acme Distributors',
        distributor_code: 'TMP-DIST-20260608-ABCD',
        distributor_is_provisional: true,
      })
    ).toBe('Acme Distributors\nTMP-DIST-20260608-ABCD');
  });

  it('does not duplicate when display equals code', () => {
    expect(
      shippingDistributorCellValue({
        distributor_display: 'TMP-DIST-20260608-ABCD',
        distributor_code: 'TMP-DIST-20260608-ABCD',
        distributor_is_provisional: true,
      })
    ).toBe('TMP-DIST-20260608-ABCD');
  });

  it('search haystack includes display and code', () => {
    const hay = shippingDistributorSearchHaystack({
      distributor_display: 'Acme',
      distributor_code: 'TMP-DIST-1',
    });
    expect(hay).toContain('Acme');
    expect(hay).toContain('TMP-DIST-1');
  });
});

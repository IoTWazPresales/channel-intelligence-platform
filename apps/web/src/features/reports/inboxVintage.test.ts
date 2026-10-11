import { describe, expect, it } from 'vitest';

import { inboxVintageLabel } from './inboxVintage';

describe('inboxVintageLabel', () => {
  it('shows the as-of instant', () => {
    expect(inboxVintageLabel({ as_of_utc: '2026-09-30T10:00:00+00:00' })).toBe(
      'Vintage 2026-09-30T10:00:00+00:00',
    );
  });

  it('stays visible when vintage is missing', () => {
    expect(inboxVintageLabel(null)).toBe('Vintage unavailable');
    expect(inboxVintageLabel({})).toBe('Vintage unavailable');
  });

  it('names a vintage that has no as-of field', () => {
    expect(inboxVintageLabel({ source: 'import' })).toBe('Vintage recorded');
  });
});

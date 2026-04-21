import { describe, expect, it } from 'vitest';

import { toQueryError } from './queryError';

describe('toQueryError', () => {
  it('returns null for nullish', () => {
    expect(toQueryError(null)).toBeNull();
    expect(toQueryError(undefined)).toBeNull();
  });

  it('passes through Error instances', () => {
    const e = new Error('nope');
    expect(toQueryError(e)).toBe(e);
  });

  it('wraps strings', () => {
    expect(toQueryError('bad')?.message).toBe('bad');
  });

  it('stringifies unknown objects', () => {
    const e = toQueryError({ code: 1 });
    expect(e?.message).toContain('code');
  });
});

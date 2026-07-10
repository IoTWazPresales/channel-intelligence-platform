import { describe, expect, it } from 'vitest';

import { importJobApplyIsLoaded } from './ImportJobLoadedSuccessCallout';

describe('importJobApplyIsLoaded', () => {
  it('returns true for loaded + completed', () => {
    expect(importJobApplyIsLoaded('loaded', 'completed')).toBe(true);
  });

  it('returns true for loaded + completed_with_errors', () => {
    expect(importJobApplyIsLoaded('loaded', 'completed_with_errors')).toBe(true);
  });

  it('returns false for validated (apply not run)', () => {
    expect(importJobApplyIsLoaded('validated', 'completed')).toBe(false);
  });

  it('returns false for loaded + running', () => {
    expect(importJobApplyIsLoaded('loaded', 'running')).toBe(false);
  });
});

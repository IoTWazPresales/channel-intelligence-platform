import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { selectionHref, useSelectionInUrl } from './useSelectionInUrl';

describe('selectionHref', () => {
  it('sets the vessel and keeps every other parameter and the hash', () => {
    expect(selectionHref('/supply/shipments?plan_quarter=26Q4#grid', { vessel: 'i:2026-09-19|2026-11-05|ZAJNB|asia_durban', cohort: '' })).toBe(
      '/supply/shipments?plan_quarter=26Q4&vessel=i%3A2026-09-19%7C2026-11-05%7CZAJNB%7Casia_durban#grid',
    );
  });

  it('sets and clears the needs-a-look cohort, and leaves another cohort alone', () => {
    expect(selectionHref('/supply/shipments', { vessel: '', cohort: 'needs_look' })).toBe('/supply/shipments?cohort=needs_look');
    expect(selectionHref('/supply/shipments?cohort=needs_look', { vessel: '', cohort: '' })).toBe('/supply/shipments');
    expect(selectionHref('/supply/shipments?cohort=overdue', { vessel: '', cohort: '' })).toBe('/supply/shipments?cohort=overdue');
  });

  it('clears the vessel', () => {
    expect(selectionHref('/supply/shipments?vessel=k1&a=1', { vessel: '', cohort: '' })).toBe('/supply/shipments?a=1');
  });
});

describe('useSelectionInUrl', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, '', '/');
  });

  it('changes the address with replaceState only: no push, no reload, and not on the first render', () => {
    window.history.replaceState(null, '', '/supply/shipments?plan_quarter=26Q4');
    const replace = vi.spyOn(window.history, 'replaceState');
    const push = vi.spyOn(window.history, 'pushState');
    const { rerender } = renderHook(({ v, c }) => useSelectionInUrl(v, c), { initialProps: { v: '', c: '' } });
    expect(replace).not.toHaveBeenCalled();
    rerender({ v: 'k1', c: '' });
    expect(replace).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe('?plan_quarter=26Q4&vessel=k1');
    rerender({ v: '', c: 'needs_look' });
    expect(window.location.search).toBe('?plan_quarter=26Q4&cohort=needs_look');
    rerender({ v: '', c: '' });
    expect(window.location.search).toBe('?plan_quarter=26Q4');
    rerender({ v: '', c: '' });
    expect(replace).toHaveBeenCalledTimes(3); // an unchanged selection writes nothing
    expect(push).not.toHaveBeenCalled();
  });
});

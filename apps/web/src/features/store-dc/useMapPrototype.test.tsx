import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MAP_PROTOTYPE_KEY, useMapPrototype } from './useMapPrototype';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('store map prototype switch', () => {
  it('defaults off and persists explicit choices across mounts', () => {
    const first = renderHook(useMapPrototype);
    expect(first.result.current[0]).toBe(false);
    act(() => first.result.current[1](true));
    expect(window.localStorage.getItem(MAP_PROTOTYPE_KEY)).toBe('true');
    first.unmount();

    const second = renderHook(useMapPrototype);
    expect(second.result.current[0]).toBe(true);
    act(() => second.result.current[1](false));
    expect(window.localStorage.getItem(MAP_PROTOTYPE_KEY)).toBe('false');
    second.unmount();
    expect(renderHook(useMapPrototype).result.current[0]).toBe(false);
  });

  it('treats malformed storage as off and survives unavailable storage', () => {
    window.localStorage.setItem(MAP_PROTOTYPE_KEY, 'yes');
    const first = renderHook(useMapPrototype);
    expect(first.result.current[0]).toBe(false);
    first.unmount();

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    const second = renderHook(useMapPrototype);
    expect(second.result.current[0]).toBe(false);
    act(() => second.result.current[1](true));
    expect(second.result.current[0]).toBe(true);
  });
});

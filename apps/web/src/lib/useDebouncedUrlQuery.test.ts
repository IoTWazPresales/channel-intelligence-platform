import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDebouncedUrlQuery } from './useDebouncedUrlQuery';

describe('useDebouncedUrlQuery', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps local input snappy and commits after idle', () => {
    const onCommit = vi.fn();
    const { result, rerender } = renderHook(
      ({ url }: { url: string }) => useDebouncedUrlQuery(url, onCommit, 300),
      { initialProps: { url: '' } },
    );

    act(() => {
      result.current[1]('a');
    });
    expect(result.current[0]).toBe('a');
    expect(onCommit).not.toHaveBeenCalled();

    act(() => {
      result.current[1]('ab');
    });
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(onCommit).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onCommit).toHaveBeenCalledWith('ab');

    // Simulate URL catching up without wiping further typing
    act(() => {
      result.current[1]('abc');
    });
    rerender({ url: 'ab' });
    expect(result.current[0]).toBe('abc');
  });

  it('syncs from external URL changes (e.g. clear filters)', () => {
    const onCommit = vi.fn();
    const { result, rerender } = renderHook(
      ({ url }: { url: string }) => useDebouncedUrlQuery(url, onCommit, 300),
      { initialProps: { url: 'foo' } },
    );
    expect(result.current[0]).toBe('foo');
    rerender({ url: '' });
    expect(result.current[0]).toBe('');
  });
});

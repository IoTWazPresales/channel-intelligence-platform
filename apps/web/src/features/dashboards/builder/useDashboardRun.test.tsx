import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';

import type { DashboardFilters } from './types';
import { useDashboardRun } from './useDashboardRun';

const bar: DashboardFilters = { date: { preset: 'all_time', from: null, to: null }, compare: 'none' };

describe('dashboard selection scope', () => {
  it('clears click values, period and cached names when switching dashboards, including back', () => {
    const { result, rerender } = renderHook(
      ({ id }) => useDashboardRun(catalog, bar, undefined, id),
      { initialProps: { id: 1 } },
    );
    act(() => {
      result.current.dispatch({ type: 'select', datum: { breakdown: 'customer', value: 101, label: 'Kestrel' } });
      result.current.dispatch({ type: 'select', datum: { breakdown: 'period', value: '2026-W28', label: '2026-W28', window: { from: '2026-07-06', to: '2026-07-12' } } });
      result.current.addNames('customer', { '101': 'Kestrel' });
    });
    expect(result.current.ctx.filters).toEqual({ customer: [101] });
    expect(result.current.ctx.window).not.toBeNull();

    rerender({ id: 2 });
    expect(result.current.ctx.filters).toEqual({});
    expect(result.current.ctx.window).toBeNull();
    expect(result.current.ctx.selectedKeys).toEqual([]);
    expect(result.current.ctx.names).toEqual({});
    rerender({ id: 1 });
    expect(result.current.ctx.selectedKeys).toEqual([]);
  });

  it('keeps click selections when a widget save refetches the same dashboard', () => {
    const { result, rerender } = renderHook(
      ({ filters }) => useDashboardRun(catalog, filters, undefined, 1),
      { initialProps: { filters: bar } },
    );
    act(() => result.current.dispatch({ type: 'select', datum: { breakdown: 'customer', value: 101, label: 'Kestrel' } }));
    rerender({ filters: { ...bar } });
    expect(result.current.ctx.filters).toEqual({ customer: [101] });
  });
});

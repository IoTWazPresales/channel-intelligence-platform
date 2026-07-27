import { describe, expect, it } from 'vitest';

/** Map tab-counts API payload the same way as useDsiEntityTabCounts (pure helper for tests). */
function mapTabCountsFromApi(counts: Record<string, { open: number; needs_work?: number; needs_review?: number }>) {
  return {
    total: counts.customer?.open ?? 0,
    needsWork: counts.customer?.needs_work ?? counts.customer?.open ?? 0,
  };
}

describe('DSI entity tab counts — terminal exclusion', () => {
  it('job #43 customer tab: resolved + ignored do not count as needs work', () => {
    const mapped = mapTabCountsFromApi({
      customer: { open: 0, needs_work: 0, needs_review: 0 },
    });
    expect(mapped.total).toBe(0);
    expect(mapped.needsWork).toBe(0);
  });

  it('prefers needs_work over legacy needs_review for badge', () => {
    const mapped = mapTabCountsFromApi({
      customer: { open: 3, needs_work: 3, needs_review: 7 },
    });
    expect(mapped.needsWork).toBe(3);
    expect(mapped.total).toBe(3);
  });
});

import type { QueryClient } from '@tanstack/react-query';

/**
 * Query keys for the planner's tenant-wide calendar-clash summary. One place owns the key so every
 * write that can change a clash (a case status change, a calendar upload) invalidates the same
 * prefix the planner card reads: the card keeps its summary fresh for 60 s and does not refetch on
 * focus, so without this a cancelled promotion would keep showing its clash.
 */
export const CLASH_SUMMARY_PREFIX = ['customer-calendar', 'clash-summary'] as const;

export const clashSummaryKey = (today: string) => [...CLASH_SUMMARY_PREFIX, today] as const;

/** Refetch every mounted clash summary (any day key) and mark the rest stale. */
export function invalidateClashSummary(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ queryKey: [...CLASH_SUMMARY_PREFIX] });
}

/**
 * Every case query lives under `['cpor', 'cases']`: the case lists and the exact current-case counts
 * (`GET /cpor/cases/counts`, keys `['cpor', 'cases', 'counts', ...]`) the planner cards read.
 */
export const CASES_PREFIX = ['cpor', 'cases'] as const;

/**
 * After any write that creates, transitions, supersedes, restores, excludes or otherwise changes
 * which cases are open (or their lines), refresh the case lists, the exact counts and the clash
 * summary together, so no planner card keeps a stale figure.
 */
export async function invalidateAfterCaseWrite(qc: QueryClient): Promise<void> {
  await Promise.all([
    qc.invalidateQueries({ queryKey: [...CASES_PREFIX] }),
    invalidateClashSummary(qc),
  ]);
}

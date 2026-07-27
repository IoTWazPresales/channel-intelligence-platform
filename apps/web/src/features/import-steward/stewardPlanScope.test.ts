import { describe, expect, it } from 'vitest';

import { nextPlanScopeCandidateIds, shrinkPlanScopeCandidateIds } from './stewardPlanScope';

describe('nextPlanScopeCandidateIds', () => {
  it('initializes from current page ids', () => {
    expect(nextPlanScopeCandidateIds([], [1, 2, 3])).toEqual([1, 2, 3]);
  });

  it('keeps scope when steward removes rows from the page cache', () => {
    expect(nextPlanScopeCandidateIds([1, 2, 3, 4], [1, 3, 4])).toEqual([1, 2, 3, 4]);
  });

  it('updates scope on pagination change', () => {
    expect(nextPlanScopeCandidateIds([1, 2, 3], [4, 5, 6])).toEqual([4, 5, 6]);
  });

  it('updates scope when rows are restored after rollback', () => {
    expect(nextPlanScopeCandidateIds([1, 2, 3], [1, 2, 3, 4])).toEqual([1, 2, 3, 4]);
  });
});

describe('shrinkPlanScopeCandidateIds', () => {
  it('removes ignored ids from frozen plan scope', () => {
    expect(shrinkPlanScopeCandidateIds([1, 2, 3, 4], [2, 99])).toEqual([1, 3, 4]);
  });

  it('allows empty scope when all ids are removed', () => {
    expect(shrinkPlanScopeCandidateIds([1], [1])).toEqual([]);
  });
});

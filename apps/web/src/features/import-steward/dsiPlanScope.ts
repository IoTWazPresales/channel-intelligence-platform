/** Keep plan query scope stable when steward actions shrink the visible page without changing pagination. */
export function nextPlanScopeCandidateIds(prev: number[], current: number[]): number[] {
  if (prev.length === 0) return current;
  const prevSet = new Set(prev);
  const isOptimisticSubsetRemoval =
    current.length < prev.length && current.every((id) => prevSet.has(id));
  if (isOptimisticSubsetRemoval) return prev;
  return current;
}

/** Remove steward-resolved or ignored ids from frozen plan scope after bulk apply. */
export function shrinkPlanScopeCandidateIds(prev: number[], removedIds: number[]): number[] {
  if (prev.length === 0 || removedIds.length === 0) return prev;
  const drop = new Set(removedIds.filter((id) => Number.isFinite(id)));
  if (drop.size === 0) return prev;
  const next = prev.filter((id) => !drop.has(id));
  return next;
}

/** Keep plan query scope stable when steward actions shrink the visible page without changing pagination. */
export function nextPlanScopeCandidateIds(prev: number[], current: number[]): number[] {
  if (prev.length === 0) return current;
  const prevSet = new Set(prev);
  const isOptimisticSubsetRemoval =
    current.length < prev.length && current.every((id) => prevSet.has(id));
  if (isOptimisticSubsetRemoval) return prev;
  return current;
}

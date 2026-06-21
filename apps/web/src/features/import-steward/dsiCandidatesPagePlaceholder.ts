/** Entity filter position in `DSI_STEWARD_CONFIG.candidatesPageQueryKey`. */
export const DSI_CANDIDATES_PAGE_ENTITY_QUERY_KEY_INDEX = 5;

/**
 * TanStack Query `placeholderData` helper: keep the previous page only when the entity
 * filter is unchanged. Prevents cross-tab placeholder rows (e.g. products) from flashing
 * while a new entity-scoped fetch is in flight.
 */
export function keepDsiCandidatesPageDataIfSameEntity<T>(
  previousData: T | undefined,
  previousQuery: { queryKey: readonly unknown[] } | undefined,
  currentEntity: string
): T | undefined {
  if (!previousData || !previousQuery) return undefined;
  const prevEntity = previousQuery.queryKey[DSI_CANDIDATES_PAGE_ENTITY_QUERY_KEY_INDEX];
  if (prevEntity !== currentEntity) return undefined;
  return previousData;
}

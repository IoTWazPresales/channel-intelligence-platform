import type { ImportStewardSelectionHeaderState } from './importStewardCandidateWorkspace.types';

export function computeImportStewardSelectionHeaderState(
  visibleRowIds: number[],
  selectedIds: Set<number>
): ImportStewardSelectionHeaderState {
  if (visibleRowIds.length === 0) return 'none';
  const n = visibleRowIds.filter((id) => selectedIds.has(id)).length;
  if (n === 0) return 'none';
  if (n === visibleRowIds.length) return 'all';
  return 'partial';
}

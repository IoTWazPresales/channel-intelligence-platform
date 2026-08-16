/** BACKLOG-047: reset mapping drafts when the bound import job id changes. */

export function mappingDraftForJobChange(
  previousJobId: number | null,
  nextJobId: number | null,
  currentDraft: Record<string, string>
): Record<string, string> {
  if (previousJobId !== nextJobId) return {};
  return currentDraft;
}

export function mappingStateMatchesJob(
  mappingStateId: number | undefined | null,
  jobId: number | null
): boolean {
  return jobId != null && mappingStateId === jobId;
}

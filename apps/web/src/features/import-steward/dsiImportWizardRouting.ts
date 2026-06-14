export type DsiWizardJobSnapshot = {
  stage: string;
  status: string;
};

/** True when validate has finished and steward/summary can mount. */
export function dsiJobHasValidationComplete(snapshot: DsiWizardJobSnapshot): boolean {
  const stage = (snapshot.stage || '').trim();
  const status = (snapshot.status || '').trim().toLowerCase();
  if (stage === 'validated' || stage === 'failed') return true;
  if (status === 'completed' || status === 'completed_with_errors') return true;
  return false;
}

/**
 * Map DSI server job state to wizard step indices (`stepsDsi`: 5 column mapping, 6 validate/steward, 7 apply).
 */
export function dsiWizardActiveStepFromServer(snapshot: DsiWizardJobSnapshot): number | null {
  const stage = (snapshot.stage || '').trim();
  const status = (snapshot.status || '').trim().toLowerCase();

  if (stage === 'loaded') return 7;

  if (dsiJobHasValidationComplete(snapshot)) return 6;

  // Validate/revalidate pipeline in flight — stay on validate step, not column mapping.
  if (status === 'running') return 6;

  if (stage === 'dsi_mapping_ready') return 5;

  if (stage === 'uploaded' || stage === 'headers_ready') return 4;

  return null;
}

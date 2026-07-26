export type ShipmentWizardJobSnapshot = {
  stage: string;
  status: string;
};

/** True when validate has finished and steward/summary can mount. */
export function shipmentJobHasValidationComplete(snapshot: ShipmentWizardJobSnapshot): boolean {
  const stage = (snapshot.stage || '').trim();
  const status = (snapshot.status || '').trim().toLowerCase();
  if (status === 'running') return false;
  if (stage === 'shipment_mapping_ready' || stage === 'mapped' || stage === 'uploaded' || stage === 'headers_ready') {
    return false;
  }
  if (stage === 'validated' || stage === 'failed') return true;
  if (status === 'completed' || status === 'completed_with_errors') return true;
  return false;
}

/** True while shipment validate/revalidate pipeline is in flight. */
export function shipmentPipelineInFlight(snapshot: ShipmentWizardJobSnapshot): boolean {
  const status = (snapshot.status || '').trim().toLowerCase();
  return status === 'running';
}

/**
 * Map shipment server job state to wizard step indices (`stepsShipmentEvidence`):
 * 3 upload · 4 column mapping · 5 validate & resolve · 6 apply
 */
export function shipmentWizardActiveStepFromServer(snapshot: ShipmentWizardJobSnapshot): number | null {
  const stage = (snapshot.stage || '').trim();
  const status = (snapshot.status || '').trim().toLowerCase();

  if (stage === 'loaded') return 6;

  if (shipmentPipelineInFlight(snapshot)) return 5;

  if (stage === 'shipment_mapping_ready' || stage === 'mapped') return 4;

  if (shipmentJobHasValidationComplete(snapshot)) return 5;

  if (stage === 'uploaded' || stage === 'headers_ready') return 3;

  return null;
}

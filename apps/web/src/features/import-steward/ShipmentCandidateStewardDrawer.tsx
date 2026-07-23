'use client';

import type { ShipmentMappingCandidateRow } from './shipmentMappingCandidateDisplay';
import { shipmentEntityChipLabel } from './shipmentMappingCandidateDisplay';
import { ShipmentMappingStewardPanel } from './ShipmentMappingStewardPanel';
import { StewardDrawerChrome } from './StewardDrawerChrome';

/** Shipment steward drawer — layout parity with {@link DsiCandidateStewardDrawer}. */
export function ShipmentCandidateStewardDrawer({
  candidate,
  planRow,
  onClose,
  applyPlanPending,
  onApplyPlanRow,
  rowActionPending,
}: {
  candidate: ShipmentMappingCandidateRow;
  planRow?: Record<string, unknown> | null;
  onClose: () => void;
  applyPlanPending?: boolean;
  onApplyPlanRow?: (candidateId: number) => void;
  rowActionPending?: boolean;
}) {
  return (
    <StewardDrawerChrome
      title={`${shipmentEntityChipLabel(candidate.entity_type)} steward`}
      onClose={onClose}
      rootTestId="shipment-candidate-steward-drawer"
      closeTestId="shipment-steward-drawer-close"
      ariaLabel="Shipment candidate steward"
    >
      <ShipmentMappingStewardPanel
        candidate={candidate}
        planRow={planRow}
        applyPlanPending={applyPlanPending}
        onApplyPlanRow={onApplyPlanRow}
        rowActionPending={rowActionPending}
      />
    </StewardDrawerChrome>
  );
}

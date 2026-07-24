'use client';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import { DsiMappingStewardPanel, type DsiCandidateRow } from './dsi-mapping-steward-panel';
import { StewardCandidateDrawer } from './StewardCandidateDrawer';

/** @deprecated Prefer {@link StewardCandidateDrawer} with evidence body slot. */
export function DsiCandidateStewardDrawer({
  importJobId,
  candidate,
  planRow,
  onClose,
  onRowActionStart,
  onRowActionEnd,
  onDone,
  onStewardFastComplete,
  lookupPeerCandidate,
  onOpenPeerByNormalizedKey,
  customerNormalizedKeysOnPage,
  duplicateClusterMembers,
}: {
  importJobId: number;
  candidate: DsiCandidateRow;
  planRow?: Record<string, unknown> | null;
  onClose: () => void;
  onRowActionStart: (candidateId: number) => void;
  onRowActionEnd: () => void;
  onDone: () => void;
  /** Drop resolved rows from in-memory plan without a full page replan. */
  onStewardFastComplete?: (candidateIds: number[]) => void;
  lookupPeerCandidate?: (normalizedKey: string) => DsiCandidateRow | null;
  onOpenPeerByNormalizedKey?: (normalizedKey: string) => void;
  customerNormalizedKeysOnPage?: readonly string[];
  duplicateClusterMembers?: readonly string[];
}) {
  const { drawerTestIds, titleForCandidate } = DSI_ENGINE_CONFIG;
  return (
    <StewardCandidateDrawer
      title={titleForCandidate(candidate)}
      onClose={onClose}
      rootTestId={drawerTestIds.root}
      closeTestId={drawerTestIds.close}
      ariaLabel={drawerTestIds.ariaLabel}
    >
      <DsiMappingStewardPanel
        importJobId={importJobId}
        candidate={candidate}
        planRow={planRow}
        onRowActionStart={onRowActionStart}
        onRowActionEnd={onRowActionEnd}
        onDone={onDone}
        onStewardFastComplete={onStewardFastComplete}
        lookupPeerCandidate={lookupPeerCandidate}
        onOpenPeerByNormalizedKey={onOpenPeerByNormalizedKey}
        customerNormalizedKeysOnPage={customerNormalizedKeysOnPage}
        duplicateClusterMembers={duplicateClusterMembers}
      />
    </StewardCandidateDrawer>
  );
}

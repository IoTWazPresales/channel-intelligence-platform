'use client';

import { StewardDrawerChrome } from './StewardDrawerChrome';
import { DsiMappingStewardPanel, type DsiCandidateRow } from './dsi-mapping-steward-panel';

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
  const title =
    candidate.entity_type === 'distributor_token'
      ? 'Distributor steward'
      : candidate.entity_type === 'product_identifier'
        ? 'Product steward'
        : 'Customer steward';

  return (
    <StewardDrawerChrome
      title={title}
      onClose={onClose}
      rootTestId="dsi-candidate-steward-drawer"
      closeTestId="dsi-steward-drawer-close"
      ariaLabel="Candidate steward"
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
    </StewardDrawerChrome>
  );
}

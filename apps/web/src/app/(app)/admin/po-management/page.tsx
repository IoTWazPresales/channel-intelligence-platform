'use client';

import { Alert } from '@mui/material';

import { PageHeader } from '@/components/PageHeader';
import { PoManagementView } from '@/features/commercial-planner/PoManagementView';
import { PoAutoLinkProposalsSection } from '@/features/commercial-planner/PoAutoLinkProposalsSection';

export default function AdminPoManagementPage() {
  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Admin' }, { label: 'PO management' }]}
        title="PO management"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Observed purchase orders are derived from <strong>shipment evidence</strong>. Linked groups show
        units-primary reconciliation against confirmed lineups; unlinked groups and the gap worklist let you
        upload a covering lineup or dismiss a PO that needs no lineup. Use <strong>Suggested PO ↔ lineup links</strong>{' '}
        to review CRAD-matched proposals before linking.
      </Alert>
      <PoManagementView />
      <PoAutoLinkProposalsSection />
    </>
  );
}

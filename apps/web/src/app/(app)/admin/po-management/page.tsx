'use client';

import { Alert } from '@mui/material';

import { PageHeader } from '@/components/PageHeader';
import { PoManagementView } from '@/features/commercial-planner/PoManagementView';

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
        upload a covering lineup or dismiss a PO that needs no lineup. <strong>Suggested PO ↔ lineup links</strong>{' '}
        (below coverage) triages CRAD-matched proposals — review and link to raise the linked count.
      </Alert>
      <PoManagementView />
    </>
  );
}

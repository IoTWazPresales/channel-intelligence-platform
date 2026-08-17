'use client';

import { Alert } from '@mui/material';
import Link from 'next/link';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { PoManagementView } from '@/features/commercial-planner/PoManagementView';

export default function AdminPoManagementPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/admin/po-management')} />
      <Alert severity="info" sx={{ mb: 2 }}>
        Observed purchase orders are derived from <strong>shipment evidence</strong>. Linked groups show
        units-primary reconciliation against confirmed lineups; unlinked groups and the gap worklist let you
        upload a covering lineup or dismiss a PO that needs no lineup. <strong>Suggested PO ↔ lineup links</strong>{' '}
        (below coverage) triages CRAD-matched proposals — review and link to raise the linked count.{' '}
        For the read-only plan-vs-executed scorecard and exception lists, see{' '}
        <Link href="/plan-vs-executed">Plan vs Executed</Link>.
      </Alert>
      <PoManagementView />
    </>
  );
}

'use client';

import { Typography } from '@mui/material';

import { PageHeader } from '@/components/PageHeader';
import { ReportBuilderView } from '@/features/reports/ReportBuilderView';

export default function ReportsPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Reports' }]} title="Report builder" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Build a governed report from the commercial semantic layer. Export Excel/PDF with data vintage on the cover,
        deliver to the inbox, or schedule Monday 07:00 UTC.
      </Typography>
      <ReportBuilderView />
    </>
  );
}

'use client';

import { Button } from '@mui/material';
import NextLink from 'next/link';

import { OverviewChrome } from '@/features/overview/OverviewChrome';
import { ReportBuilderView } from '@/features/reports/ReportBuilderView';

export default function ReportsPage() {
  return (
    <OverviewChrome
      title="Reports"
      description="Ask a question of the same figures as Stock, Planning and the Case book: pick a figure, choose how to break it down, and run it. Export Excel or PDF with the as-of date on the cover, send it to the inbox, or schedule it."
      meta={null}
      actions={
        <Button component={NextLink} href="/inbox" size="small" variant="outlined" sx={{ whiteSpace: 'nowrap' }}>
          Report inbox
        </Button>
      }
    >
      <ReportBuilderView />
    </OverviewChrome>
  );
}

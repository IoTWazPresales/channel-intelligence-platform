'use client';

import { Link, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { PageHeader } from '@/components/PageHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';

export default function PricingPage() {
  return (
    <WorkbenchCanvas>
      <PageHeader
        crumbs={[{ label: 'Planning' }, { label: 'Recorded prices' }]}
        title="Recorded prices"
      />
      <Stack spacing={2}>
        <Typography>
          Recorded prices was retired. Prices now come from the line-up retail price and the latest
          shelf price seen on customer listings
        </Typography>
        <Stack direction="row" spacing={2}>
          <Link component={NextLink} href="/lineup">
            Line-up
          </Link>
          <Link component={NextLink} href="/listing-capture?tab=registry">
            Customer listings
          </Link>
        </Stack>
      </Stack>
    </WorkbenchCanvas>
  );
}

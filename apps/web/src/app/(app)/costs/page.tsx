'use client';

import { Paper } from '@mui/material';

import { PageHeader } from '@/components/PageHeader';
import { SkuEconomicsImport } from '@/features/commercial-planner/SkuEconomicsImport';
import { navPageChrome } from '@/features/shell/navPageChrome';

export default function CostsPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/costs')} />
      <Paper sx={{ p: 2 }}>
        <SkuEconomicsImport />
      </Paper>
    </>
  );
}

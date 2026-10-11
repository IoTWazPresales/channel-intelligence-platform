'use client';

import { Stack } from '@mui/material';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

export default function CporClaimsPage() {
  return (
    <FundingChrome>
      <Panel
        title="Upload the claim file on the case"
        subtitle="Claim evidence is uploaded on the case settlement desk. Apply happens there too."
        flush
      >
        <Stack spacing={0.25} sx={{ px: 1, pb: 1, mt: 2 }} data-testid="funding-claims">
          <PanelRow
            severity="neutral"
            primary="Open a case and upload the claim file"
            secondary="The file is uploaded on that case's settlement desk. Settlement happens there too."
            href="/commercial-planner/cpor-cases"
          />
        </Stack>
      </Panel>
    </FundingChrome>
  );
}

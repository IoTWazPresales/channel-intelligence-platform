'use client';

import { Stack } from '@mui/material';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

export default function CporClaimsPage() {
  return (
    <FundingChrome>
      <Panel
        title="Import claim evidence, then settle on the case"
        subtitle="Claim files are stewarded in Import Center (cpor_claim_evidence). Apply still happens on the case settlement desk — this leaf does not invent a second importer."
        flush
      >
        <Stack spacing={0.25} sx={{ px: 1, pb: 1, mt: 2 }} data-testid="funding-claims">
          <PanelRow
            severity="neutral"
            primary="Import claim evidence"
            secondary="Opens Import Center with cpor_claim_evidence selected."
            href="/admin/imports?template=cpor_claim_evidence"
          />
          <PanelRow
            severity="neutral"
            primary="Open Case book to settle"
            secondary="Pick a case, then settle on the case desk."
            href="/commercial-planner/cpor-cases"
          />
        </Stack>
      </Panel>
    </FundingChrome>
  );
}

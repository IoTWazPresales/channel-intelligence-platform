'use client';

import { Stack, Typography } from '@mui/material';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { Panel } from '@/features/workbench-ui/Panel';

export default function BudgetsPage() {
  return (
    <FundingChrome>
      <Panel
        sx={{ mt: 2 }}
        title={
          <Stack direction="row" spacing={1} alignItems="center">
            <span>Budget ledger</span>
            <CapabilityStatus status="substrate" />
          </Stack>
        }
      >
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760 }}>
          Allocation, commitment, and actual are not recorded yet. The planner’s budget check uses
          the lineup-derived profit reservation instead, and says so on the figure. When a budget
          import lands, this view shows allocation against what has been drawn, per programme and
          period. Until then the ledger stays empty.
        </Typography>
      </Panel>
    </FundingChrome>
  );
}

'use client';

import { Stack, Typography } from '@mui/material';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { Panel } from '@/features/workbench-ui/Panel';

export default function BudgetsPage() {
  return (
    <>
      <FundingChrome />
      <Panel
        title={
          <Stack direction="row" spacing={1} alignItems="center">
            <span>Budget ledger — data only</span>
            <CapabilityStatus status="substrate" />
          </Stack>
        }
      >
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760 }}>
          Allocation → commitment → actual tables (fact_budget_*) exist with no writer and no rows
          (verified empty on cip). The planner’s budget check uses the lineup-derived profit
          reservation instead, and says so on the figure. When a budget import or ledger writer
          lands, this lens shows allocation vs drawn per programme and period; until then nothing is
          shown rather than a placeholder.
        </Typography>
      </Panel>
    </>
  );
}

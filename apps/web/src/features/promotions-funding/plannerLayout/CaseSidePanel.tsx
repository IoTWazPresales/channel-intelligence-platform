'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { formatDualMoneyLine } from '@/features/cpor/fxDisplay';
import { fmtInt } from '@/features/promotions-funding/format';
import { ORIGIN_LABEL, STAGE_LABEL, stageTone, type PlanStage } from '@/features/promotions-funding/lifecycle';
import type { CporCaseListRow } from '@/features/promotions-funding/types';
import { Panel } from '@/features/workbench-ui/Panel';
import { StatusChip } from '@/features/workbench-ui/controls';

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ textAlign: 'right' }}>
        {children}
      </Typography>
    </Stack>
  );
}

/**
 * Selected case summary. The quantity, export and economics actions stay in PlanWorkspace;
 * this panel only opens it (onOpen). Customer shows by name only, never the code.
 */
export function CaseSidePanel({
  row,
  onOpen,
  onClear,
}: {
  row: CporCaseListRow | null;
  onOpen: (id: number) => void;
  onClear: () => void;
}) {
  if (!row) {
    return (
      <Panel title="Case">
        <Typography variant="body2" color="text.secondary" data-testid="planner-side-panel-empty">
          Select a case on the timeline, the grid or the action queue to see its summary here.
        </Typography>
      </Panel>
    );
  }
  const support = formatDualMoneyLine(row.ttl_support_zar, {
    currencyCode: row.currency_code,
    roeSnapshot: row.roe_snapshot,
    missingRoe: Boolean(row.missing_roe) || row.fx_booked === false,
  });
  const flags = row.flags ?? [];
  return (
    <Box data-testid="planner-side-panel">
    <Panel
      title={row.case_name || row.case_code}
      subtitle={row.case_code}
      actions={<StatusChip label={STAGE_LABEL[row.status as PlanStage] ?? row.status} tone={stageTone(row.status)} />}
    >
      <Stack spacing={1}>
        <Fact label="Customer">{row.customer_name ?? '—'}</Fact>
        <Fact label="Promotion type">{row.promotion_type}</Fact>
        <Fact label="Window">
          {row.window_start ?? '—'} → {row.window_end ?? '—'}
        </Fact>
        <Fact label="Origin">{ORIGIN_LABEL[String(row.origin ?? 'native')] ?? String(row.origin ?? '')}</Fact>
        <Fact label="Lines">{row.line_count ?? 0}</Fact>
        <Fact label="Est. units">{fmtInt(row.estimate_qty_sum)}</Fact>
        <Fact label="Support">
          {support.local}
          <Box component="span" sx={{ display: 'block' }}>
            <Typography variant="caption" color="text.secondary">
              {support.usdLine}
            </Typography>
          </Box>
        </Fact>
        {row.needs_reapproval ? (
          <Typography variant="caption" color="warning.main">
            Reapproval required (money ceiling).
          </Typography>
        ) : null}
        {flags.length ? (
          <Typography variant="caption" color="text.secondary">
            Flags: {flags.join(' · ')}
          </Typography>
        ) : null}
        <Stack direction="row" spacing={1} sx={{ pt: 0.5 }}>
          <Button size="small" variant="contained" onClick={() => onOpen(row.id)} data-testid="planner-side-open">
            Open plan
          </Button>
          <Button
            size="small"
            variant="outlined"
            component={NextLink}
            href={`/commercial-planner/cpor-cases?status=${encodeURIComponent(row.status)}`}
          >
            Case book
          </Button>
          <Button size="small" onClick={onClear} data-testid="planner-side-clear">
            Clear
          </Button>
        </Stack>
      </Stack>
    </Panel>
    </Box>
  );
}

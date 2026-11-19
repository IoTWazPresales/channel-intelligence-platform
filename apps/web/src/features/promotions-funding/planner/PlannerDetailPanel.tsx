'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';
import type { ReactNode } from 'react';

import { formatDualMoneyLine } from '@/features/cpor/fxDisplay';
import { evidenceBasisLabel } from '@/features/promotions-funding/evidenceBasis';
import { fmtInt } from '@/features/promotions-funding/format';
import { STAGE_LABEL, stageTone, type PlanStage } from '@/features/promotions-funding/lifecycle';
import type { ActionItem } from '@/features/promotions-funding/plannerLayout/actionQueue';
import type { CporCaseListRow } from '@/features/promotions-funding/types';
import { Panel } from '@/features/workbench-ui/Panel';
import { StatusChip } from '@/features/workbench-ui/controls';

import { NOT_AVAILABLE_YET } from './PlannerKpiCard';

type SectionState = 'ready' | 'unavailable' | 'unknown';

function Section({
  id,
  title,
  state = 'ready',
  children,
}: {
  id: string;
  title: string;
  state?: SectionState;
  children: ReactNode;
}) {
  return (
    <Box data-testid={`planner-detail-${id}`} data-state={state} sx={{ py: 0.75, borderTop: 1, borderColor: 'divider' }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 11 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function NotAvailable({ reason }: { reason: string }) {
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
        {NOT_AVAILABLE_YET}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {reason}
      </Typography>
    </>
  );
}

/**
 * Detail of the selected promotion: support, expected units, stock health, linked claims, evidence, risks and
 * next actions. Each section reads what the case list already carries; a section with no source yet says
 * "Not available yet" and why (never a made-up figure), and is not the same thing as a failed or empty read.
 */
export function PlannerDetailPanel({
  row,
  unavailableId = null,
  actions,
  onOpen,
  onClear,
}: {
  row: CporCaseListRow | null;
  /** A case is selected but no loaded list holds its row (a list failed or has moved on). */
  unavailableId?: number | null;
  /** What the action queue says waits on this case; undefined while the queue is loading, failed or partial. */
  actions?: readonly ActionItem[];
  onOpen: (id: number) => void;
  onClear: () => void;
}) {
  if (!row && unavailableId != null) {
    return (
      <Box data-testid="planner-detail">
        <Panel title="Promotion detail">
          <Stack spacing={1} data-testid="planner-detail-unavailable">
            <Typography variant="body2" color="error">
              The detail for this promotion could not be loaded. The plan workspace still opens it.
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="contained" onClick={() => onOpen(unavailableId)} data-testid="planner-side-open">
                Open plan
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
  if (!row) {
    return (
      <Box data-testid="planner-detail">
        <Panel title="Promotion detail">
          <Typography variant="body2" color="text.secondary" data-testid="planner-detail-empty">
            Select a promotion on the timeline, the list or the action queue to see its support, units, stock health,
            claims, evidence, risks and next actions here.
          </Typography>
        </Panel>
      </Box>
    );
  }

  const support = formatDualMoneyLine(row.ttl_support_zar, {
    currencyCode: row.currency_code,
    roeSnapshot: row.roe_snapshot,
    missingRoe: Boolean(row.missing_roe) || row.fx_booked === false,
  });
  const claimCount = row.settle_readiness ? (row.settle_readiness.claim_evidence_count ?? 0) : null;
  const basis = row.evidence_basis ?? row.settle_readiness?.evidence_basis ?? null;
  const risks: string[] = [];
  if (row.needs_reapproval) risks.push('Reapproval required (money ceiling).');
  for (const f of row.flags ?? []) risks.push(f);
  for (const a of actions ?? []) if (a.overdue) risks.push(a.hint);

  return (
    <Box data-testid="planner-detail">
      <Panel
        title={row.case_name || row.case_code}
        subtitle={`${row.case_code} · ${row.customer_name ?? '—'} · ${row.window_start ?? '—'} → ${row.window_end ?? '—'}`}
        actions={<StatusChip label={STAGE_LABEL[row.status as PlanStage] ?? row.status} tone={stageTone(row.status)} />}
      >
        <Stack spacing={0}>
          <Section id="support" title="Support">
            <Typography variant="body2">{support.local}</Typography>
            <Typography variant="caption" color="text.secondary">
              {support.usdLine}
            </Typography>
          </Section>
          <Section id="units" title="Expected units">
            <Typography variant="body2">{fmtInt(row.estimate_qty_sum)}</Typography>
            <Typography variant="caption" color="text.secondary">
              {row.line_count ?? 0} line{(row.line_count ?? 0) === 1 ? '' : 's'}, as entered on the plan
            </Typography>
          </Section>
          <Section id="stock" title="Stock health" state="unavailable">
            <NotAvailable reason="Stock health will come from the customer's sell-through stock; no figure is shown until then." />
          </Section>
          {claimCount == null ? (
            <Section id="claims" title="Linked claims" state="unavailable">
              <NotAvailable reason="This case list carries no claim summary for the case. Open the plan to see its claims." />
            </Section>
          ) : (
            <Section id="claims" title="Linked claims">
              <Typography variant="body2">
                {claimCount} claim file{claimCount === 1 ? '' : 's'} applied
              </Typography>
              {row.payment_evidence_count != null ? (
                <Typography variant="caption" color="text.secondary">
                  {row.payment_evidence_count} payment evidence record{row.payment_evidence_count === 1 ? '' : 's'}
                </Typography>
              ) : null}
            </Section>
          )}
          <Section id="evidence" title="Evidence">
            <Typography variant="body2">{evidenceBasisLabel(basis)}</Typography>
          </Section>
          <Section id="risks" title="Risks">
            {risks.length > 0 ? (
              risks.map((r) => (
                <Typography key={r} variant="body2" color="warning.main">
                  {r}
                </Typography>
              ))
            ) : (
              <Typography variant="body2">No risk flags recorded on this case.</Typography>
            )}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              Stock and funding risks are not available yet.
            </Typography>
          </Section>
          <Section id="next-actions" title="Next actions" state={actions ? 'ready' : 'unknown'}>
            {actions == null ? (
              <Typography variant="body2" color="text.secondary">
                Unknown: the action queue is still loading, failed or is only partly loaded.
              </Typography>
            ) : actions.length === 0 ? (
              <Typography variant="body2">Nothing waiting on this case.</Typography>
            ) : (
              actions.map((a) => (
                <Typography key={a.key} variant="body2">
                  {a.hint}
                </Typography>
              ))
            )}
          </Section>
          <Stack direction="row" spacing={1} sx={{ pt: 1 }} flexWrap="wrap" useFlexGap>
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

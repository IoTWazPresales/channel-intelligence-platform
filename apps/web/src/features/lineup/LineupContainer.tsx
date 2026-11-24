'use client';

import { Box, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { LineupWorkspace } from '@/features/lineup/LineupWorkspace';
import {
  formatUnits,
  isPendingApproval,
  type LineupPlanRow,
} from '@/features/lineup/lineupTypes';
import { useLineupNetRequirement } from '@/features/lineup/useLineupNetRequirement';
import {
  filterLineupRowsByExactProductId,
  filterLineupRowsBySlice,
  parseExactLineupProductId,
  parseLineupApprovalFilter,
  parseLineupSlice,
} from '@/features/lineup/lineupViews';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

function LineupContainerInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const approval = parseLineupApprovalFilter(searchParams?.get('approval'));
  const productId = parseExactLineupProductId(searchParams?.get('product'));
  const slice = parseLineupSlice(searchParams?.get('customer'), searchParams?.get('period'));

  const { data: items } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
    staleTime: 30_000,
  });
  const { data: netReq } = useLineupNetRequirement(true);
  const { data: pve } = useQuery({
    queryKey: ['plan-vs-executed', 'lineup-read'],
    queryFn: ({ signal }) =>
      apiGet<{ scorecard?: { fill_rate?: number | null }; data_unavailable?: boolean }>(
        '/api/v1/plan-vs-executed',
        { signal },
      ),
    staleTime: 120_000,
  });

  const rows = items ?? [];
  const slicedRows = filterLineupRowsBySlice(rows, slice);
  const scopedRows = productId == null ? slicedRows : filterLineupRowsByExactProductId(slicedRows, productId);
  // Headlines describe the selected slice/product across all approval statuses.
  // The scope summary also accounts for the grid's pending-only filter.
  const plannedUnits = scopedRows.reduce((s, r) => s + (Number(r.planned_volume_units) || 0), 0);
  const decided = scopedRows.filter((r) => r.approval_status === 'approved' || r.approval_status === 'rejected');
  const approved = scopedRows.filter((r) => r.approval_status === 'approved').length;
  const approvalPct = decided.length > 0 ? Math.round((approved / decided.length) * 100) : 0;
  const pendingCount = scopedRows.filter((r) => isPendingApproval(r.approval_status)).length;
  const visibleCount = approval === 'pending' ? pendingCount : scopedRows.length;
  const netTotal =
    netReq?.data_unavailable === false
      ? Math.round((netReq.rows ?? []).reduce((s, r) => s + (r.net_requirement || 0), 0))
      : null;
  const fillPct =
    pve?.data_unavailable || pve?.scorecard?.fill_rate == null
      ? null
      : Math.round((pve.scorecard.fill_rate ?? 0) * 100);

  const setQuery = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams?.toString() ?? '');
    mutate(params);
    const q = params.toString();
    router.replace(q ? `/lineup/cases?${q}` : '/lineup/cases', { scroll: false });
  };

  const setApproval = (next: 'all' | 'pending') => {
    setQuery((params) => {
      if (next === 'pending') params.set('approval', 'pending');
      else params.delete('approval');
    });
  };

  const clearProduct = () => {
    setQuery((params) => {
      params.delete('product');
    });
  };

  const clearSlice = () => {
    setQuery((params) => {
      params.delete('customer');
      params.delete('period');
    });
  };

  const clearScope = () => {
    setQuery((params) => {
      params.delete('approval');
      params.delete('product');
      params.delete('customer');
      params.delete('period');
    });
  };

  const sliceChipLabel = (() => {
    if (!slice) return null;
    const hit = rows.find((r) => r.customer_id === slice.customerId && r.period_start === slice.periodStart);
    const who = hit?.customer_name || hit?.customer_code || `Customer ${slice.customerId}`;
    return `${who} · ${hit?.period_label || slice.periodStart}`;
  })();

  const productChipLabel = (() => {
    if (productId == null) return null;
    const hit = rows.find((r) => r.product_id === productId);
    const sku = hit?.sku?.trim();
    return sku ? `Product · ${sku}` : `Product · ${productId}`;
  })();

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1.5 }} data-testid="lineup-container">
      <Box data-testid="lineup-cases-strip">
        <HeadlineStrip columns={5}>
          <HeadlineFigure
            testId="lineup-planned-units"
            label="Planned units"
            value={scopedRows.length ? formatUnits(plannedUnits) : '—'}
            compact
            caption={`${scopedRows.length} plan lines (all statuses)`}
          />
          <HeadlineFigure
            label="Net requirement"
            value={netTotal != null ? formatUnits(netTotal) : '—'}
            compact
            caption="Master scope; bias included"
          />
          <HeadlineFigure
            testId="lineup-approval"
            label="Approval"
            value={scopedRows.length ? `${approvalPct}%` : '—'}
            compact
            caption="of decided lines in scope"
          />
          <HeadlineFigure
            testId="lineup-pending-approval"
            label="Pending approval"
            value={scopedRows.length ? pendingCount : '—'}
            compact
            severity={pendingCount ? 'warn' : 'good'}
            onClick={() => setApproval(approval === 'pending' ? 'all' : 'pending')}
          />
          <HeadlineFigure
            label="Plan coverage"
            value={fillPct != null ? `${fillPct}%` : '—'}
            compact
            caption="Master scope; shipped against lineup"
          />
        </HeadlineStrip>
      </Box>
      <Box data-testid="lineup-scope-bar">
        <ScopeBar
          chips={[
            {
              key: 'all',
              label: 'All lines',
              active: approval === 'all' && productId == null && slice == null,
              onToggle: () => clearScope(),
            },
            {
              key: 'pending',
              label: `Pending approval · ${pendingCount}`,
              active: approval === 'pending',
              onToggle: () => setApproval(approval === 'pending' ? 'all' : 'pending'),
              tone: 'warning',
            },
            ...(sliceChipLabel
              ? [
                  {
                    key: 'slice',
                    label: sliceChipLabel,
                    active: true,
                    onToggle: clearSlice,
                  },
                ]
              : []),
            ...(productChipLabel
              ? [
                  {
                    key: 'product',
                    label: productChipLabel,
                    active: true,
                    onToggle: clearProduct,
                  },
                ]
              : []),
          ]}
          summary={
            productId == null && approval === 'all'
              ? `${visibleCount} plan lines`
              : `${visibleCount} of ${slicedRows.length} plan lines`
          }
          onClear={clearScope}
          clearAvailable={productId != null || approval === 'pending' || slice != null}
        />
      </Box>
      <Typography
        data-testid="lineup-reporting-note"
        sx={{ fontSize: '12px', color: 'text.secondary', m: 0 }}
      >
        Reporting customers only.
      </Typography>
      <LineupWorkspace />
    </Box>
  );
}

export function LineupContainer() {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}>Loading Lineup…</Box>}>
      <LineupContainerInner />
    </Suspense>
  );
}

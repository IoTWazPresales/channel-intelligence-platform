'use client';

import { Box } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { LineupWorkspace } from '@/features/lineup/LineupWorkspace';
import {
  formatUnits,
  isPendingApproval,
  type LineupPlanRow,
  type NetRequirementResponse,
} from '@/features/lineup/lineupTypes';
import {
  filterLineupRowsByExactProductId,
  parseExactLineupProductId,
  parseLineupApprovalFilter,
} from '@/features/lineup/lineupViews';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

function LineupContainerInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const approval = parseLineupApprovalFilter(searchParams?.get('approval'));
  const productId = parseExactLineupProductId(searchParams?.get('product'));

  const { data: items } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
    staleTime: 30_000,
  });
  const { data: netReq } = useQuery({
    queryKey: ['lineup-net-requirement', 'headline'],
    queryFn: ({ signal }) =>
      apiGet<NetRequirementResponse>(
        '/api/v1/lineup/net-requirement?limit=200&include_customer_shares=false&apply_bias=true',
        { signal },
      ),
    staleTime: 60_000,
  });
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
  const scopedRows = productId == null ? rows : filterLineupRowsByExactProductId(rows, productId);
  const plannedUnits = rows.reduce((s, r) => s + (Number(r.planned_volume_units) || 0), 0);
  const decided = rows.filter((r) => r.approval_status === 'approved' || r.approval_status === 'rejected');
  const approved = rows.filter((r) => r.approval_status === 'approved').length;
  const approvalPct = decided.length > 0 ? Math.round((approved / decided.length) * 100) : rows.length ? 0 : 0;
  const pendingCount = rows.filter((r) => isPendingApproval(r.approval_status)).length;
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

  const clearScope = () => {
    setQuery((params) => {
      params.delete('approval');
      params.delete('product');
    });
  };

  const productChipLabel = (() => {
    if (productId == null) return null;
    const hit = rows.find((r) => r.product_id === productId);
    const sku = hit?.sku?.trim();
    return sku ? `Product · ${sku}` : `Product · ${productId}`;
  })();

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, gap: 1.5, pt: 1.5 }} data-testid="lineup-container">
      <Box data-testid="lineup-cases-strip">
        <HeadlineStrip columns={5}>
          <HeadlineFigure
            label="Planned units"
            value={rows.length ? formatUnits(plannedUnits) : '—'}
            compact
            caption={`${rows.length} plan lines`}
          />
          <HeadlineFigure
            label="Net requirement"
            value={netTotal != null ? formatUnits(netTotal) : '—'}
            compact
            caption="B2 apply-bias"
          />
          <HeadlineFigure
            label="Approval"
            value={rows.length ? `${approvalPct}%` : '—'}
            compact
            caption="of decided lines"
          />
          <HeadlineFigure
            label="Pending approval"
            value={rows.length ? pendingCount : '—'}
            compact
            severity={pendingCount ? 'warn' : 'good'}
            onClick={() => setApproval(approval === 'pending' ? 'all' : 'pending')}
          />
          <HeadlineFigure
            label="Plan coverage"
            value={fillPct != null ? `${fillPct}%` : '—'}
            compact
            caption="shipped against lineup"
          />
        </HeadlineStrip>
      </Box>
      <Box data-testid="lineup-scope-bar">
        <ScopeBar
          chips={[
            {
              key: 'all',
              label: 'All lines',
              active: approval === 'all' && productId == null,
              onToggle: () => clearScope(),
            },
            {
              key: 'pending',
              label: `Pending approval · ${pendingCount}`,
              active: approval === 'pending',
              onToggle: () => setApproval(approval === 'pending' ? 'all' : 'pending'),
              tone: 'warning',
            },
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
            productId == null
              ? `${rows.length} plan lines`
              : `${scopedRows.length} of ${rows.length} plan lines`
          }
          onClear={clearScope}
          clearAvailable={productId != null || approval === 'pending'}
        />
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <LineupWorkspace />
      </Box>
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

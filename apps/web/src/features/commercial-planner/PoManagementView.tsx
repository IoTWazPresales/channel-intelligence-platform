'use client';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import type { ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { OPS_LIST_GRID_PAGINATION } from '@/features/shell/opsListGridPagination';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { PoAutoLinkProposalsSection, PO_AUTO_LINK_SECTION_ID } from './PoAutoLinkProposalsSection';
import { PoCaseLinkWorklistSection } from './PoCaseLinkWorklistSection';
import { CustomerTokenWorklistSection } from './CustomerTokenWorklistSection';
import { DistributorAttributionReviewSection } from './DistributorAttributionReviewSection';
import { LineupDuplicatePartitionPanel } from './LineupDuplicatePartitionPanel';
import { PoDismissReasonDialog } from './PoDismissReasonDialog';
import { buildPlanVsExecutedHref } from '@/features/plan-vs-executed/productDisplay';

type BacklogGroup = {
  year: number;
  quarter: number;
  quarter_label: string;
  product_line: string;
  shipped_units: number;
  shipped_value_cost: number;
  shipped_value_plan: number;
  fx_complete: boolean;
  po_count: number;
  linked_po_count: number;
  status: 'linked' | 'unlinked';
  linked_case_ids?: number[];
  lineup_case_exists?: boolean;
  parse_incomplete?: boolean;
  upload_prompt?: { period_label: string | null; product_line: string };
};

type BacklogResponse = { groups: BacklogGroup[]; data_unavailable?: boolean };

type CoverageResponse = {
  total_pos_observed: number;
  total_pos_linked: number;
  first_run: boolean;
  data_unavailable?: boolean;
};

type GapRow = {
  purchase_order_id: number;
  po_number_raw: string | null;
  product_id: number;
  product_name: string | null;
  product_line: string | null;
  shipped_units: number;
  period_label: string;
  dismissed: boolean;
  quarter_label?: string;
  row_key?: string;
};

type GapGroup = {
  year: number;
  quarter: number;
  quarter_label: string;
  rows: GapRow[];
  shipped_units: number;
  po_count: number;
  product_count: number;
};

type GapResponse = {
  groups: GapGroup[];
  dismissed: { purchase_order_id: number; po_number_raw: string | null; dismiss_reason_code: string | null }[];
  total_gap_rows: number;
  data_unavailable?: boolean;
};

function fmtUnits(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat().format(Math.round(n));
}

function fmtValue(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

function poGroupDomId(g: Pick<BacklogGroup, 'year' | 'quarter' | 'product_line'>): string {
  return `po-mgmt-group-${g.year}-${g.quarter}-${g.product_line}`;
}

export const PO_BACKLOG_SECTION_ID = 'po-mgmt-backlog';
export const PO_GAP_SECTION_ID = 'po-mgmt-gap';

function needsLineupUpload(g: BacklogGroup): boolean {
  return g.status === 'unlinked' && !g.lineup_case_exists && !g.parse_incomplete;
}

export function PoManagementView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);
  const [dismissTarget, setDismissTarget] = useState<GapRow | null>(null);
  const [pendingLinkProposals, setPendingLinkProposals] = useState(0);
  const [highlightGroupId, setHighlightGroupId] = useState<string | null>(null);
  const [highlightCustomerId, setHighlightCustomerId] = useState<number | null>(null);

  const deepLinkPeriod = searchParams.get('period');
  const deepLinkBU = searchParams.get('business_unit');
  const deepLinkCustomerRaw = searchParams.get('customer_id');
  const deepLinkCustomerId = deepLinkCustomerRaw ? Number.parseInt(deepLinkCustomerRaw, 10) : null;

  const scrollToAutoLink = () => {
    document.getElementById(PO_AUTO_LINK_SECTION_ID)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const coverageQ = useQuery({
    queryKey: ['po-management', 'coverage'],
    queryFn: ({ signal }) => apiGet<CoverageResponse>('/api/v1/po-management/coverage', { signal }),
  });
  const backlogQ = useQuery({
    queryKey: ['po-management', 'backlog'],
    queryFn: ({ signal }) => apiGet<BacklogResponse>('/api/v1/po-management/backlog', { signal }),
  });

  useEffect(() => {
    if (!deepLinkPeriod || backlogQ.data?.data_unavailable || !backlogQ.data?.groups?.length) return;
    const match = backlogQ.data.groups.find(
      (g) =>
        g.quarter_label === deepLinkPeriod && (!deepLinkBU || g.product_line === deepLinkBU),
    );
    if (!match) return;
    const groupId = poGroupDomId(match);
    setHighlightGroupId(groupId);
    if (deepLinkCustomerId != null && !Number.isNaN(deepLinkCustomerId)) {
      setHighlightCustomerId(deepLinkCustomerId);
    }
    const timer = window.setTimeout(() => {
      document.getElementById(groupId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 150);
    return () => window.clearTimeout(timer);
  }, [backlogQ.data, deepLinkPeriod, deepLinkBU, deepLinkCustomerId]);
  const gapQ = useQuery({
    queryKey: ['po-management', 'gap', showDismissed],
    queryFn: ({ signal }) =>
      apiGet<GapResponse>(
        `/api/v1/commercial-planner/lineup/po-gap-worklist?include_dismissed=${showDismissed ? 'true' : 'false'}`,
        { signal }
      ),
  });

  const dismissMut = useMutation({
    mutationFn: (vars: { purchase_order_id: number; reason_code: string }) =>
      apiPost('/api/v1/commercial-planner/lineup/po-gap-worklist/dismiss', vars),
    onSuccess: () => {
      setDismissTarget(null);
      void qc.invalidateQueries({ queryKey: ['po-management', 'gap'] });
    },
  });
  const restoreMut = useMutation({
    mutationFn: (purchaseOrderId: number) =>
      apiPost(
        `/api/v1/commercial-planner/lineup/po-gap-worklist/restore?purchase_order_id=${purchaseOrderId}`,
        undefined
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['po-management', 'gap'] });
    },
  });

  const startUpload = (periodLabel: string | null) => {
    const params = new URLSearchParams({ unified: '1' });
    if (periodLabel) params.set('period', periodLabel);
    router.push(`/admin/imports?${params.toString()}`);
  };

  const viewShipmentsForPo = (poId: number, label: string | null) => {
    const params = new URLSearchParams({ purchase_order_id: String(poId) });
    if (label) params.set('po_label', label);
    router.push(`/shipping?${params.toString()}`);
  };

  const coverage = coverageQ.data;
  const backlog = backlogQ.data;
  const gap = gapQ.data;
  const loading = coverageQ.isLoading || backlogQ.isLoading;

  const gapRows = useMemo<GapRow[]>(() => {
    if (!gap?.groups.length) return [];
    return gap.groups.flatMap((g) =>
      g.rows.map((r) => ({
        ...r,
        quarter_label: g.quarter_label,
        row_key: `${g.year}-${g.quarter}-${r.purchase_order_id}-${r.product_id}`,
      }))
    );
  }, [gap]);

  const worklistSummary = useMemo(() => {
    const observed = coverage?.total_pos_observed ?? 0;
    const linked = coverage?.total_pos_linked ?? 0;
    const unlinkedPos = Math.max(observed - linked, 0);
    const uploadNeeded =
      backlog?.groups.filter((g) => g.po_count > 0 && needsLineupUpload(g)).length ?? 0;
    const gapCount = gap?.total_gap_rows ?? 0;
    return { unlinkedPos, uploadNeeded, gapCount };
  }, [coverage, backlog, gap]);

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const gapColumnDefs = useMemo<ColDef<GapRow>[]>(
    () => [
      { headerName: 'Period', field: 'quarter_label', width: 90 },
      {
        headerName: 'PO',
        width: 130,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const row = p.data;
          if (!row) return null;
          return (
            <Button
              size="small"
              variant="text"
              onClick={() => viewShipmentsForPo(row.purchase_order_id, row.po_number_raw)}
            >
              {row.po_number_raw ?? `#${row.purchase_order_id}`}
            </Button>
          );
        },
      },
      {
        headerName: 'Product',
        flex: 1,
        minWidth: 140,
        valueGetter: (p) => p.data?.product_name ?? (p.data ? `#${p.data.product_id}` : ''),
      },
      { headerName: 'Line', field: 'product_line', width: 120 },
      {
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        field: 'shipped_units',
        valueFormatter: (p) => fmtUnits(p.value as number),
      },
      {
        headerName: 'Actions',
        colId: 'actions',
        width: 110,
        pinned: 'right',
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const row = p.data;
          if (!row) return null;
          if (row.dismissed) {
            return (
              <Button
                size="small"
                onClick={() => restoreMut.mutate(row.purchase_order_id)}
                disabled={restoreMut.isPending}
                data-testid={`gap-restore-${row.purchase_order_id}`}
              >
                Restore
              </Button>
            );
          }
          return (
            <Button
              size="small"
              color="warning"
              onClick={() => setDismissTarget(row)}
              disabled={dismissMut.isPending}
              data-testid={`gap-dismiss-${row.purchase_order_id}`}
            >
              Dismiss
            </Button>
          );
        },
      },
    ],
    [dismissMut.isPending, restoreMut]
  );

  const gapGridOptions = useMemo<GridOptions<GapRow>>(
    () => ({
      getRowId: (p) => p.data.row_key ?? `${p.data.purchase_order_id}-${p.data.product_id}`,
      ...OPS_LIST_GRID_PAGINATION,
    }),
    []
  );

  return (
    <Stack spacing={3}>
      <LineupDuplicatePartitionPanel />
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            PO coverage
          </Typography>
          {loading ? (
            <LinearProgress data-testid="po-coverage-loading" />
          ) : coverage?.data_unavailable ? (
            <Alert severity="info">
              PO coverage is unavailable — no shipment evidence with purchase orders has been imported yet.
            </Alert>
          ) : (
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <Chip
                color="primary"
                label={`${coverage?.total_pos_observed ?? 0} POs observed`}
                data-testid="po-coverage-observed"
              />
              <Chip
                color={coverage?.total_pos_linked ? 'success' : 'default'}
                variant={coverage?.total_pos_linked ? 'filled' : 'outlined'}
                label={`${coverage?.total_pos_linked ?? 0} linked to a lineup`}
                data-testid="po-coverage-linked"
              />
              {pendingLinkProposals > 0 ? (
                <Chip
                  clickable
                  color="warning"
                  variant="filled"
                  onClick={scrollToAutoLink}
                  label={`${pendingLinkProposals} CRAD link suggestion${pendingLinkProposals === 1 ? '' : 's'}`}
                  data-testid="po-coverage-pending-links"
                />
              ) : null}
              {coverage?.first_run ? (
                <Alert severity="warning" sx={{ flex: 1, minWidth: 280 }}>
                  First run — no confirmed lineups link to any observed PO yet. Upload a lineup for a period below to
                  start reconciling.
                </Alert>
              ) : null}
            </Stack>
          )}
        </CardContent>
      </Card>

      {!loading && !coverage?.data_unavailable ? (
        <Card variant="outlined" data-testid="po-worklist-summary">
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              What needs action
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              <Chip
                clickable={worklistSummary.unlinkedPos > 0}
                onClick={() => scrollToSection(PO_BACKLOG_SECTION_ID)}
                label={`${worklistSummary.unlinkedPos} PO${worklistSummary.unlinkedPos === 1 ? '' : 's'} unlinked`}
                color={worklistSummary.unlinkedPos > 0 ? 'warning' : 'default'}
                variant={worklistSummary.unlinkedPos > 0 ? 'filled' : 'outlined'}
                data-testid="po-worklist-unlinked"
              />
              <Chip
                clickable={worklistSummary.uploadNeeded > 0}
                onClick={() => scrollToSection(PO_BACKLOG_SECTION_ID)}
                label={`${worklistSummary.uploadNeeded} period×BU need lineup upload`}
                color={worklistSummary.uploadNeeded > 0 ? 'error' : 'default'}
                variant={worklistSummary.uploadNeeded > 0 ? 'filled' : 'outlined'}
                data-testid="po-worklist-upload-needed"
              />
              <Chip
                clickable={worklistSummary.gapCount > 0}
                onClick={() => scrollToSection(PO_GAP_SECTION_ID)}
                label={`${worklistSummary.gapCount.toLocaleString()} gap line${worklistSummary.gapCount === 1 ? '' : 's'}`}
                color={worklistSummary.gapCount > 0 ? 'warning' : 'default'}
                variant={worklistSummary.gapCount > 0 ? 'filled' : 'outlined'}
                data-testid="po-worklist-gaps"
              />
              <Typography variant="caption" color="text.secondary">
                Reconciliation outcomes live on Execution vs plan — this page is the operational worklist only.
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      <PoCaseLinkWorklistSection />

      <CustomerTokenWorklistSection />

      <DistributorAttributionReviewSection />

      <PoAutoLinkProposalsSection autoFetch onPendingCountChange={setPendingLinkProposals} />

      <Box id={PO_BACKLOG_SECTION_ID}>
        <Typography variant="h6" gutterBottom>
          Observed purchase orders by period & product line
        </Typography>
        {backlogQ.isLoading ? (
          <LinearProgress />
        ) : backlog?.data_unavailable ? (
          <Alert severity="info">No observed purchase orders to report.</Alert>
        ) : !backlog?.groups.length ? (
          <Alert severity="info">No purchase orders observed in shipment history yet.</Alert>
        ) : (
          <Stack spacing={1.5}>
            {backlog.groups.map((g) => (
              <Card
                key={`${g.year}-${g.quarter}-${g.product_line}`}
                id={poGroupDomId(g)}
                variant="outlined"
                sx={
                  highlightGroupId === poGroupDomId(g)
                    ? { borderColor: 'warning.main', borderWidth: 2, boxShadow: 2 }
                    : undefined
                }
              >
                <CardContent>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    alignItems={{ sm: 'center' }}
                    justifyContent="space-between"
                  >
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={g.quarter_label} color="default" />
                      <Typography variant="subtitle1" fontWeight={600}>
                        {g.product_line}
                      </Typography>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={g.status === 'linked' ? `${g.linked_po_count}/${g.po_count} POs linked` : `${g.po_count} POs`}
                        color={g.status === 'linked' ? 'success' : 'default'}
                      />
                    </Stack>
                    {g.status !== 'linked' ? (
                      <Stack direction="row" spacing={2} alignItems="center">
                        <Typography variant="body2" color="text.secondary">
                          {fmtUnits(g.shipped_units)} units observed
                        </Typography>
                        <Tooltip
                          title={
                            g.fx_complete
                              ? 'Shipped value bridged to plan currency'
                              : 'FX unavailable for some SKUs — value is best-effort'
                          }
                        >
                          <Typography variant="body2" color="text.secondary">
                            {fmtValue(g.fx_complete ? g.shipped_value_plan : g.shipped_value_cost)}
                            {g.fx_complete ? ' (plan)' : ' (cost · FX partial)'}
                          </Typography>
                        </Tooltip>
                      </Stack>
                    ) : null}
                  </Stack>

                  <Divider sx={{ my: 1.5 }} />

                  {g.status === 'linked' ? (
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
                      <Typography variant="body2" color="text.secondary" data-testid={`po-linked-status-${g.year}-${g.quarter}-${g.product_line}`}>
                        Linked {g.linked_po_count}/{g.po_count} POs — operational linking complete for this group.
                      </Typography>
                      <Button
                        component={Link}
                        href={buildPlanVsExecutedHref({
                          periodFrom: g.quarter_label,
                          periodTo: g.quarter_label,
                          productLine: g.product_line,
                        })}
                        variant="contained"
                        size="small"
                        color="primary"
                        data-testid={`po-pve-link-${g.year}-${g.quarter}-${g.product_line}`}
                      >
                        Execution vs plan outcomes
                      </Button>
                      {highlightCustomerId != null && highlightGroupId === poGroupDomId(g) ? (
                        <Typography variant="caption" color="warning.main">
                          Highlighted customer #{highlightCustomerId} — link or upload work above; reconciliation
                          outcomes are on Execution vs plan.
                        </Typography>
                      ) : null}
                    </Stack>
                  ) : g.lineup_case_exists ? (
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Chip size="small" color="info" label="Lineup on file" />
                      <Typography variant="caption" color="text.secondary">
                        A lineup case exists for {g.quarter_label} {g.product_line} — link POs via suggested
                        auto-links above.
                      </Typography>
                    </Stack>
                  ) : g.parse_incomplete ? (
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Chip size="small" color="warning" label="Parse incomplete" />
                      <Typography variant="caption" color="text.secondary">
                        Lineup file uploaded for {g.quarter_label} {g.product_line} but lines were not parsed —
                        re-run parse from Import Center.
                      </Typography>
                    </Stack>
                  ) : (
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => startUpload(g.upload_prompt?.period_label ?? g.quarter_label)}
                        data-testid={`po-upload-${g.year}-${g.quarter}-${g.product_line}`}
                      >
                        Upload lineup for this period
                      </Button>
                      <Typography variant="caption" color="text.secondary">
                        Pre-fills the unified lineup importer with period {g.quarter_label}.
                      </Typography>
                    </Stack>
                  )}
                </CardContent>
              </Card>
            ))}
          </Stack>
        )}
      </Box>

      <Box id={PO_GAP_SECTION_ID}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="h6">POs with shipments but no covering lineup</Typography>
          <Button size="small" onClick={() => setShowDismissed((v) => !v)} data-testid="toggle-dismissed">
            {showDismissed ? 'Hide dismissed' : 'Show dismissed'}
          </Button>
        </Stack>
        {dismissMut.isError ? <Alert severity="error">{safeDisplayError(dismissMut.error)}</Alert> : null}
        {gapQ.isLoading ? (
          <LinearProgress />
        ) : gap?.data_unavailable ? (
          <Alert severity="info">Gap worklist is unavailable.</Alert>
        ) : !gap?.groups.length ? (
          <Alert severity="success">No gaps — every shipment PO is covered by a confirmed lineup.</Alert>
        ) : (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
              <Typography variant="body2" color="text.secondary">
                {gap.total_gap_rows} gap row{gap.total_gap_rows === 1 ? '' : 's'} across {gap.groups.length} period
                {gap.groups.length === 1 ? '' : 's'}
              </Typography>
              <Button
                size="small"
                variant="outlined"
                onClick={() => startUpload(gap.groups[0]?.quarter_label ?? null)}
                data-testid="gap-upload-top"
              >
                Upload lineup
              </Button>
            </Stack>
            <Box data-testid="po-gap-grid">
              <EnterpriseDataGrid
                rowData={gapRows}
                columnDefs={gapColumnDefs}
                gridOptions={gapGridOptions}
                height={480}
              />
            </Box>
          </Stack>
        )}
      </Box>

      <PoDismissReasonDialog
        open={!!dismissTarget}
        title="Dismiss gap PO"
        description={
          dismissTarget
            ? `PO ${dismissTarget.po_number_raw ?? `#${dismissTarget.purchase_order_id}`} has no covering lineup.`
            : undefined
        }
        defaultReason="no lineup needed"
        isPending={dismissMut.isPending}
        error={dismissMut.isError ? safeDisplayError(dismissMut.error) : null}
        onClose={() => setDismissTarget(null)}
        onConfirm={(reason) => {
          if (!dismissTarget) return;
          dismissMut.mutate({ purchase_order_id: dismissTarget.purchase_order_id, reason_code: reason });
        }}
      />
    </Stack>
  );
}

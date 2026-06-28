'use client';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type ReconSummary = {
  matched?: number;
  short?: number;
  over?: number;
  unshipped?: number;
  unplanned?: number;
  amended?: number;
  po_no_match?: number;
};

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
  reconciliation_summary?: ReconSummary;
  linked_case_ids?: number[];
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

function ReconSummaryChips({ summary }: { summary: ReconSummary }) {
  const items: { key: keyof ReconSummary; label: string; color: 'success' | 'warning' | 'error' | 'info' | 'default' }[] = [
    { key: 'matched', label: 'matched', color: 'success' },
    { key: 'short', label: 'short', color: 'warning' },
    { key: 'over', label: 'over', color: 'warning' },
    { key: 'unshipped', label: 'unshipped', color: 'error' },
    { key: 'amended', label: 'amended', color: 'info' },
    { key: 'unplanned', label: 'unplanned', color: 'info' },
    { key: 'po_no_match', label: 'po no match', color: 'error' },
  ];
  const active = items.filter((it) => (summary[it.key] ?? 0) > 0);
  if (!active.length) return <Chip size="small" variant="outlined" label="No reconciled lines yet" />;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {active.map((it) => (
        <Chip key={it.key} size="small" color={it.color} label={`${summary[it.key]} ${it.label}`} />
      ))}
    </Stack>
  );
}

export function PoManagementView() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);

  const coverageQ = useQuery({
    queryKey: ['po-management', 'coverage'],
    queryFn: ({ signal }) => apiGet<CoverageResponse>('/api/v1/po-management/coverage', { signal }),
  });
  const backlogQ = useQuery({
    queryKey: ['po-management', 'backlog'],
    queryFn: ({ signal }) => apiGet<BacklogResponse>('/api/v1/po-management/backlog', { signal }),
  });
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

  const handleDismiss = (row: GapRow) => {
    const reason = window.prompt(
      `Dismiss PO ${row.po_number_raw ?? `#${row.purchase_order_id}`} (no covering lineup)?\nReason (e.g. "no lineup needed", "out of scope"):`,
      'no lineup needed'
    );
    if (reason == null) return;
    const trimmed = reason.trim();
    if (!trimmed) return;
    dismissMut.mutate({ purchase_order_id: row.purchase_order_id, reason_code: trimmed });
  };

  const coverage = coverageQ.data;
  const backlog = backlogQ.data;
  const gap = gapQ.data;
  const loading = coverageQ.isLoading || backlogQ.isLoading;

  return (
    <Stack spacing={3}>
      {/* Coverage meter */}
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

      {/* Backlog: observed PO groups */}
      <Box>
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
              <Card key={`${g.year}-${g.quarter}-${g.product_line}`} variant="outlined">
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
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Typography variant="body2" color="text.secondary">
                        {fmtUnits(g.shipped_units)} units
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
                  </Stack>

                  <Divider sx={{ my: 1.5 }} />

                  {g.status === 'linked' ? (
                    <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Typography variant="body2" color="text.secondary">
                        Reconciliation:
                      </Typography>
                      {g.reconciliation_summary ? <ReconSummaryChips summary={g.reconciliation_summary} /> : null}
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

      {/* Gap worklist */}
      <Box>
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
            {gap.groups.map((g) => (
              <Card key={`gap-${g.year}-${g.quarter}`} variant="outlined">
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Chip size="small" label={g.quarter_label} />
                      <Typography variant="body2" color="text.secondary">
                        {g.po_count} PO{g.po_count === 1 ? '' : 's'} · {g.product_count} product
                        {g.product_count === 1 ? '' : 's'} · {fmtUnits(g.shipped_units)} units
                      </Typography>
                    </Stack>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => startUpload(g.quarter_label)}
                      data-testid={`gap-upload-${g.year}-${g.quarter}`}
                    >
                      Upload lineup
                    </Button>
                  </Stack>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>PO</TableCell>
                        <TableCell>Product</TableCell>
                        <TableCell>Line</TableCell>
                        <TableCell align="right">Units</TableCell>
                        <TableCell align="right">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {g.rows.map((r) => (
                        <TableRow
                          key={`${r.purchase_order_id}-${r.product_id}`}
                          sx={r.dismissed ? { opacity: 0.5 } : undefined}
                        >
                          <TableCell>
                            <Button
                              size="small"
                              variant="text"
                              onClick={() => viewShipmentsForPo(r.purchase_order_id, r.po_number_raw)}
                            >
                              {r.po_number_raw ?? `#${r.purchase_order_id}`}
                            </Button>
                          </TableCell>
                          <TableCell>{r.product_name ?? `#${r.product_id}`}</TableCell>
                          <TableCell>{r.product_line ?? '—'}</TableCell>
                          <TableCell align="right">{fmtUnits(r.shipped_units)}</TableCell>
                          <TableCell align="right">
                            {r.dismissed ? (
                              <Button
                                size="small"
                                onClick={() => restoreMut.mutate(r.purchase_order_id)}
                                disabled={restoreMut.isPending}
                                data-testid={`gap-restore-${r.purchase_order_id}`}
                              >
                                Restore
                              </Button>
                            ) : (
                              <Button
                                size="small"
                                color="warning"
                                onClick={() => handleDismiss(r)}
                                disabled={dismissMut.isPending}
                                startIcon={dismissMut.isPending ? <CircularProgress size={14} /> : undefined}
                                data-testid={`gap-dismiss-${r.purchase_order_id}`}
                              >
                                Dismiss
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  );
}

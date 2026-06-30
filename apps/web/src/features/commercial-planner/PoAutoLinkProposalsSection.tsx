'use client';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import type { ColDef, GridApi, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { PoDismissReasonDialog } from './PoDismissReasonDialog';
import { currentQuarterLabel } from './poPeriodUtils';

type MatchedProduct = {
  product_id: number;
  sku?: string | null;
  sales_model_name?: string | null;
  marketing_name?: string | null;
  planned_units: number;
  shipped_units: number;
  open_order_units?: number;
};

export type PoAutoLinkProposal = {
  proposal_key: string;
  case_id: number;
  case_period_label: string | null;
  inferred_period_start: string | null;
  customer_id: number | null;
  customer_label: string | null;
  distributor_id: number | null;
  distributor_code: string | null;
  distributor_name: string | null;
  purchase_order_id: number;
  po_number: string | null;
  po_number_norm: string | null;
  confidence: 'high' | 'medium';
  reason: string;
  date_source: string;
  dismissed?: boolean;
  matched_products: MatchedProduct[];
  total_planned_units: number;
  total_shipped_units: number;
};

type ProposalsResponse = {
  proposals: PoAutoLinkProposal[];
  total: number;
  returned: number;
  dismissed?: { proposal_key: string; case_id: number; purchase_order_id: number; reason_code: string | null }[];
  dismissed_count?: number;
  data_unavailable?: boolean;
};

function fmtUnits(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

function confidenceColor(c: string): 'success' | 'warning' | 'default' {
  if (c === 'high') return 'success';
  if (c === 'medium') return 'warning';
  return 'default';
}

function reasonLabel(reason: string): string {
  const map: Record<string, string> = {
    customer_product_crad_in_period: 'Customer + product + CRAD in period',
    customer_product_date_fallback_in_period: 'Customer + product + ship date in period',
    product_period_customer_unresolved: 'Product + period (customer unresolved)',
  };
  return map[reason] ?? reason;
}

function productDisplayLabel(m: MatchedProduct): string {
  const parts = [m.sales_model_name, m.sku].filter(Boolean);
  if (parts.length) return parts.join(' · ');
  if (m.marketing_name) return m.marketing_name;
  return `Product #${m.product_id}`;
}

function PoAutoLinkConfirmDialog({
  open,
  proposal,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  open: boolean;
  proposal: PoAutoLinkProposal | null;
  onClose: () => void;
  onConfirm: (notes: string) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [notes, setNotes] = useState('');

  if (!proposal) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="po-auto-link-confirm-dialog">
      <DialogTitle>Link PO to lineup case</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            This links the observed purchase order to the lineup case and sets the case to{' '}
            <strong>PO issued</strong>. Review customer and product overlap before confirming.
          </Typography>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Customer
            </Typography>
            <Typography variant="body1" data-testid="confirm-customer-label">
              {proposal.customer_label ?? (proposal.customer_id ? `Customer #${proposal.customer_id}` : 'Unresolved')}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={proposal.case_period_label ?? proposal.inferred_period_start ?? '—'} />
            <Chip size="small" color={confidenceColor(proposal.confidence)} label={proposal.confidence} />
            <Chip size="small" variant="outlined" label={reasonLabel(proposal.reason)} />
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>PO</TableCell>
                <TableCell>Distributor</TableCell>
                <TableCell align="right">Planned</TableCell>
                <TableCell align="right">Shipped</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>{proposal.po_number ?? `#${proposal.purchase_order_id}`}</TableCell>
                <TableCell>
                  {[proposal.distributor_code, proposal.distributor_name].filter(Boolean).join(' — ') || '—'}
                </TableCell>
                <TableCell align="right">{fmtUnits(proposal.total_planned_units)}</TableCell>
                <TableCell align="right">{fmtUnits(proposal.total_shipped_units)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          {proposal.matched_products.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Matched products ({proposal.matched_products.length})
              </Typography>
              <Table size="small" data-testid="po-auto-link-matched-products-table">
                <TableHead>
                  <TableRow>
                    <TableCell>Product</TableCell>
                    <TableCell align="right">Planned</TableCell>
                    <TableCell align="right">Shipped</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {proposal.matched_products.map((m) => (
                    <TableRow key={m.product_id} data-testid={`matched-product-${m.product_id}`}>
                      <TableCell>
                        <Tooltip title={`Product ID ${m.product_id}`}>
                          <span data-testid={`matched-product-label-${m.product_id}`}>{productDisplayLabel(m)}</span>
                        </Tooltip>
                        {m.marketing_name && m.sales_model_name ? (
                          <Typography variant="caption" color="text.secondary" display="block">
                            {m.marketing_name}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right">{fmtUnits(m.planned_units)}</TableCell>
                      <TableCell align="right">{fmtUnits(m.shipped_units)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />
          {error && (
            <Alert severity="error" data-testid="po-auto-link-confirm-error">
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose} disabled={isPending}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={isPending}
          onClick={() => onConfirm(notes)}
          data-testid="po-auto-link-confirm-submit"
        >
          {isPending ? 'Linking…' : 'Link PO to case'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function PoAutoLinkProposalsSection() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [period, setPeriod] = useState(() => currentQuarterLabel());
  const [confidence, setConfidence] = useState<'all' | 'high' | 'medium'>('all');
  const [showDismissed, setShowDismissed] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmProposal, setConfirmProposal] = useState<PoAutoLinkProposal | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [dismissTarget, setDismissTarget] = useState<PoAutoLinkProposal | null>(null);
  const gridApiRef = useRef<GridApi<PoAutoLinkProposal> | null>(null);

  const queryKey = ['po-auto-link', period, confidence, showDismissed] as const;

  const proposalsQ = useQuery({
    queryKey,
    enabled: expanded,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ limit: '200' });
      if (period.trim()) params.set('period', period.trim());
      if (confidence !== 'all') params.set('confidence', confidence);
      if (showDismissed) params.set('include_dismissed', 'true');
      return apiGet<ProposalsResponse>(
        `/api/v1/commercial-planner/lineup/po-auto-link/proposals?${params.toString()}`,
        { signal }
      );
    },
  });

  const applyMut = useMutation({
    mutationFn: (vars: { items: { case_id: number; purchase_order_id: number; notes?: string }[]; notes?: string }) =>
      apiPost('/api/v1/commercial-planner/lineup/po-auto-link/apply', vars),
    onSuccess: (data: { error_count?: number; errors?: { error: string }[] }) => {
      setApplyError(data.error_count ? data.errors?.map((e) => e.error).join('; ') ?? 'Some links failed' : null);
      setConfirmProposal(null);
      setSelected(new Set());
      gridApiRef.current?.deselectAll();
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
      void qc.invalidateQueries({ queryKey: ['po-management'] });
      void qc.invalidateQueries({ queryKey: ['lineup-cases'] });
    },
    onError: (e) => setApplyError(safeDisplayError(e)),
  });

  const dismissMut = useMutation({
    mutationFn: (vars: {
      proposal_key: string;
      case_id: number;
      purchase_order_id: number;
      reason_code: string;
    }) => apiPost('/api/v1/commercial-planner/lineup/po-auto-link/dismiss', vars),
    onSuccess: () => {
      setDismissTarget(null);
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
    },
  });

  const restoreMut = useMutation({
    mutationFn: (proposalKey: string) =>
      apiPost(
        `/api/v1/commercial-planner/lineup/po-auto-link/restore?proposal_key=${encodeURIComponent(proposalKey)}`,
        undefined
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
    },
  });

  const proposals = proposalsQ.data?.proposals ?? [];
  const dismissedList = proposalsQ.data?.dismissed ?? [];
  const activeProposals = useMemo(
    () => (showDismissed ? proposals : proposals.filter((p) => !p.dismissed)),
    [proposals, showDismissed]
  );

  const bulkApply = () => {
    const items = activeProposals
      .filter((p) => selected.has(p.proposal_key) && !p.dismissed)
      .map((p) => ({ case_id: p.case_id, purchase_order_id: p.purchase_order_id }));
    if (!items.length) return;
    setApplyError(null);
    applyMut.mutate({ items });
  };

  const selectAllHigh = () => {
    const keys = activeProposals.filter((p) => p.confidence === 'high' && !p.dismissed).map((p) => p.proposal_key);
    setSelected(new Set(keys));
    if (!gridApiRef.current) return;
    gridApiRef.current.forEachNode((node) => {
      if (node.data && keys.includes(node.data.proposal_key)) node.setSelected(true);
      else node.setSelected(false);
    });
  };

  const handleSingleConfirm = (notes: string) => {
    if (!confirmProposal) return;
    setApplyError(null);
    applyMut.mutate({
      items: [
        {
          case_id: confirmProposal.case_id,
          purchase_order_id: confirmProposal.purchase_order_id,
          notes: notes.trim() || undefined,
        },
      ],
    });
  };

  const columnDefs = useMemo<ColDef<PoAutoLinkProposal>[]>(
    () => [
      {
        headerName: 'Confidence',
        field: 'confidence',
        width: 110,
        cellRenderer: (p: ICellRendererParams<PoAutoLinkProposal>) =>
          p.data ? (
            <Tooltip title={reasonLabel(p.data.reason)}>
              <Chip size="small" color={confidenceColor(p.data.confidence)} label={p.data.confidence} />
            </Tooltip>
          ) : null,
      },
      {
        headerName: 'Period',
        width: 100,
        valueGetter: (p) => p.data?.case_period_label ?? p.data?.inferred_period_start ?? '—',
      },
      { headerName: 'Customer', flex: 1, minWidth: 140, field: 'customer_label' },
      {
        headerName: 'PO',
        width: 130,
        valueGetter: (p) => p.data?.po_number ?? (p.data ? `#${p.data.purchase_order_id}` : ''),
      },
      {
        headerName: 'Distributor',
        flex: 1,
        minWidth: 120,
        valueGetter: (p) =>
          p.data
            ? [p.data.distributor_code, p.data.distributor_name].filter(Boolean).join(' — ') || '—'
            : '',
      },
      {
        headerName: 'Planned',
        width: 100,
        type: 'numericColumn',
        valueGetter: (p) => p.data?.total_planned_units ?? null,
        valueFormatter: (p) => fmtUnits(p.value as number),
      },
      {
        headerName: 'Shipped',
        width: 100,
        type: 'numericColumn',
        valueGetter: (p) => p.data?.total_shipped_units ?? null,
        valueFormatter: (p) => fmtUnits(p.value as number),
      },
      {
        headerName: 'Actions',
        colId: 'actions',
        width: 160,
        pinned: 'right',
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<PoAutoLinkProposal>) => {
          const row = p.data;
          if (!row) return null;
          if (row.dismissed) {
            return (
              <Button
                size="small"
                onClick={() => restoreMut.mutate(row.proposal_key)}
                disabled={restoreMut.isPending}
              >
                Restore
              </Button>
            );
          }
          return (
            <Stack direction="row" spacing={0.5}>
              <Button
                size="small"
                onClick={() => {
                  setApplyError(null);
                  setConfirmProposal(row);
                }}
                data-testid={`po-auto-link-review-${row.proposal_key}`}
              >
                Review
              </Button>
              <Button size="small" color="warning" onClick={() => setDismissTarget(row)}>
                Dismiss
              </Button>
            </Stack>
          );
        },
      },
    ],
    [restoreMut]
  );

  const gridOptions = useMemo<GridOptions<PoAutoLinkProposal>>(
    () => ({
      getRowId: (p) => p.data.proposal_key,
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
        isRowSelectable: (p) => !p.data?.dismissed,
      },
      onGridReady: (e) => {
        gridApiRef.current = e.api;
      },
      onSelectionChanged: (e) => {
        const keys = e.api.getSelectedRows().map((r) => r.proposal_key);
        setSelected(new Set(keys));
      },
    }),
    []
  );

  const requestExpand = useCallback(() => {
    setExpanded(true);
  }, []);

  return (
    <Card variant="outlined" data-testid="po-auto-link-section">
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" useFlexGap>
            <Box>
              <Typography variant="h6" gutterBottom>
                Suggested PO ↔ lineup links
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Triage tool — compute CRAD-matched proposals on demand. Review and link, or dismiss bad suggestions.
              </Typography>
            </Box>
            {!expanded ? (
              <Button
                variant="contained"
                size="small"
                onClick={requestExpand}
                data-testid="po-auto-link-expand"
              >
                Compute / show suggested links
              </Button>
            ) : (
              <Button size="small" variant="outlined" onClick={() => setExpanded(false)} data-testid="po-auto-link-collapse">
                Collapse
              </Button>
            )}
          </Stack>

          <Collapse in={expanded}>
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
                <TextField
                  size="small"
                  label="Period filter"
                  placeholder="e.g. 26Q1"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  sx={{ minWidth: 140 }}
                  data-testid="po-auto-link-period"
                />
                <FormControl size="small" sx={{ minWidth: 140 }}>
                  <InputLabel id="po-auto-link-confidence-label">Confidence</InputLabel>
                  <Select
                    labelId="po-auto-link-confidence-label"
                    label="Confidence"
                    value={confidence}
                    onChange={(e) => setConfidence(e.target.value as 'all' | 'high' | 'medium')}
                    data-testid="po-auto-link-confidence"
                  >
                    <MenuItem value="all">All</MenuItem>
                    <MenuItem value="high">High only</MenuItem>
                    <MenuItem value="medium">Medium only</MenuItem>
                  </Select>
                </FormControl>
                <Button size="small" onClick={() => void proposalsQ.refetch()} disabled={proposalsQ.isFetching}>
                  Refresh
                </Button>
                <Button size="small" onClick={() => setShowDismissed((v) => !v)} data-testid="po-auto-link-toggle-dismissed">
                  {showDismissed ? 'Hide dismissed' : 'Show dismissed'}
                </Button>
                <Button size="small" onClick={selectAllHigh} disabled={!activeProposals.some((p) => p.confidence === 'high')}>
                  Select all high
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  disabled={selected.size === 0 || applyMut.isPending}
                  onClick={bulkApply}
                  data-testid="po-auto-link-bulk-apply"
                >
                  Link selected ({selected.size})
                </Button>
              </Stack>

              {proposalsQ.isLoading ? (
                <Typography variant="body2" color="text.secondary" data-testid="po-auto-link-loading">
                  Computing proposals…
                </Typography>
              ) : proposalsQ.data?.data_unavailable ? (
                <Alert severity="info">Auto-link proposals are temporarily unavailable.</Alert>
              ) : !activeProposals.length && !showDismissed ? (
                <Alert severity="info" data-testid="po-auto-link-empty">
                  No link proposals for the current filters. Try clearing the period filter or lowering confidence.
                </Alert>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary">
                    Showing {activeProposals.length} of {proposalsQ.data?.total ?? 0} proposals
                    {(proposalsQ.data?.dismissed_count ?? 0) > 0
                      ? ` · ${proposalsQ.data?.dismissed_count} dismissed`
                      : ''}
                  </Typography>
                  <Box data-testid="po-auto-link-table">
                    <EnterpriseDataGrid
                      rowData={activeProposals}
                      columnDefs={columnDefs}
                      gridOptions={gridOptions}
                      height={420}
                    />
                  </Box>
                </>
              )}

              {showDismissed && dismissedList.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Dismissed ({dismissedList.length})
                  </Typography>
                  <Stack spacing={0.5}>
                    {dismissedList.map((d) => (
                      <Stack key={d.proposal_key} direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" color="text.secondary">
                          {d.proposal_key} — {d.reason_code}
                        </Typography>
                        <Button size="small" onClick={() => restoreMut.mutate(d.proposal_key)}>
                          Restore
                        </Button>
                      </Stack>
                    ))}
                  </Stack>
                </Box>
              )}

              {applyError && !confirmProposal && <Alert severity="error">{applyError}</Alert>}
            </Stack>
          </Collapse>
        </Stack>
      </CardContent>

      <PoAutoLinkConfirmDialog
        open={!!confirmProposal}
        proposal={confirmProposal}
        onClose={() => {
          setConfirmProposal(null);
          setApplyError(null);
        }}
        onConfirm={handleSingleConfirm}
        isPending={applyMut.isPending}
        error={applyError}
      />

      <PoDismissReasonDialog
        open={!!dismissTarget}
        title="Dismiss link proposal"
        description={
          dismissTarget
            ? `PO ${dismissTarget.po_number ?? dismissTarget.purchase_order_id} ↔ case ${dismissTarget.case_id}`
            : undefined
        }
        defaultReason="wrong match"
        isPending={dismissMut.isPending}
        error={dismissMut.isError ? safeDisplayError(dismissMut.error) : null}
        onClose={() => setDismissTarget(null)}
        onConfirm={(reason) => {
          if (!dismissTarget) return;
          dismissMut.mutate({
            proposal_key: dismissTarget.proposal_key,
            case_id: dismissTarget.case_id,
            purchase_order_id: dismissTarget.purchase_order_id,
            reason_code: reason,
          });
        }}
      />
    </Card>
  );
}

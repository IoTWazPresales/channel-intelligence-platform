'use client';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
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
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type InputHTMLAttributes } from 'react';

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
  total_open_order_units?: number;
};

type GroupCoverageEntry = {
  group_key: string;
  linked_shipped_units: number;
};

type ProposalsResponse = {
  proposals: PoAutoLinkProposal[];
  total: number;
  returned: number;
  dismissed?: { proposal_key: string; case_id: number; purchase_order_id: number; reason_code: string | null }[];
  dismissed_count?: number;
  data_unavailable?: boolean;
  group_coverage?: GroupCoverageEntry[];
  group_coverage_by_key?: Record<string, GroupCoverageEntry>;
};

export type PoAutoLinkProposalGroup = {
  groupKey: string;
  case_period_label: string | null;
  inferred_period_start: string | null;
  customer_id: number | null;
  customer_label: string | null;
  groupPlanUnits: number;
  proposedShipUnits: number;
  proposedPipelineUnits: number;
  linkedShipUnits: number;
  proposals: PoAutoLinkProposal[];
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

function customerDisplayLabel(p: PoAutoLinkProposal): string {
  if (p.customer_label?.trim()) return p.customer_label.trim();
  if (p.customer_id != null) return `Customer #${p.customer_id}`;
  return 'Unresolved customer';
}

function periodSortKey(g: PoAutoLinkProposalGroup): string {
  return g.inferred_period_start ?? g.case_period_label ?? '';
}

export function dedupeGroupPlanUnits(proposals: PoAutoLinkProposal[]): number {
  const byProduct = new Map<number, number>();
  for (const p of proposals) {
    for (const m of p.matched_products) {
      byProduct.set(m.product_id, Math.max(byProduct.get(m.product_id) ?? 0, m.planned_units));
    }
  }
  return [...byProduct.values()].reduce((sum, n) => sum + n, 0);
}

function sumProposedShipUnits(proposals: PoAutoLinkProposal[]): number {
  return proposals.reduce((sum, p) => sum + (p.total_shipped_units ?? 0), 0);
}

function sumProposedPipelineUnits(proposals: PoAutoLinkProposal[]): number {
  return proposals.reduce((sum, p) => sum + (p.total_open_order_units ?? 0), 0);
}

export function formatCoverageLineParts({
  planUnits,
  proposedShipUnits,
  proposedPipelineUnits,
  linkedShipUnits,
}: {
  planUnits: number;
  proposedShipUnits: number;
  proposedPipelineUnits: number;
  linkedShipUnits: number;
}): string {
  const parts: string[] = [`Plan ${fmtUnits(planUnits)}`];
  if (proposedShipUnits > 0 || proposedPipelineUnits > 0) {
    let proposed = `shipped ${fmtUnits(proposedShipUnits)}`;
    if (proposedPipelineUnits > 0) {
      proposed += ` + pipeline ${fmtUnits(proposedPipelineUnits)} proposed`;
    } else if (proposedShipUnits > 0) {
      proposed += ' proposed';
    }
    parts.push(proposed);
  }
  if (linkedShipUnits > 0) {
    parts.push(`${fmtUnits(linkedShipUnits)} already linked`);
  }
  return parts.join(' · ');
}

function sortProposalsInGroup(proposals: PoAutoLinkProposal[]): PoAutoLinkProposal[] {
  return [...proposals].sort((a, b) => {
    const conf = (b.confidence === 'high' ? 1 : 0) - (a.confidence === 'high' ? 1 : 0);
    if (conf !== 0) return conf;
    const poA = a.po_number ?? String(a.purchase_order_id);
    const poB = b.po_number ?? String(b.purchase_order_id);
    return poA.localeCompare(poB);
  });
}

export function buildProposalGroups(
  proposals: PoAutoLinkProposal[],
  coverageByKey?: Record<string, GroupCoverageEntry>,
): PoAutoLinkProposalGroup[] {
  const groups = new Map<string, PoAutoLinkProposal[]>();
  for (const p of proposals) {
    const period = p.case_period_label ?? p.inferred_period_start ?? '';
    const key = `${period}|${p.customer_id ?? 'null'}`;
    const bucket = groups.get(key) ?? [];
    bucket.push(p);
    groups.set(key, bucket);
  }

  return [...groups.entries()]
    .map(([groupKey, bucket]) => {
      const first = bucket[0];
      return {
        groupKey,
        case_period_label: first.case_period_label,
        inferred_period_start: first.inferred_period_start,
        customer_id: first.customer_id,
        customer_label: first.customer_label,
        groupPlanUnits: dedupeGroupPlanUnits(bucket),
        proposedShipUnits: sumProposedShipUnits(bucket),
        proposedPipelineUnits: sumProposedPipelineUnits(bucket),
        linkedShipUnits: coverageByKey?.[groupKey]?.linked_shipped_units ?? 0,
        proposals: sortProposalsInGroup(bucket),
      };
    })
    .sort((a, b) => {
      const periodCmp = periodSortKey(b).localeCompare(periodSortKey(a));
      if (periodCmp !== 0) return periodCmp;
      return customerDisplayLabel(a.proposals[0]).localeCompare(customerDisplayLabel(b.proposals[0]));
    });
}

/** @deprecated Use buildProposalGroups — kept for tests migrating off synthetic grid rows. */
export function buildGroupedPoAutoLinkRows(proposals: PoAutoLinkProposal[]) {
  return buildProposalGroups(proposals);
}

function MatchedProductsChip({ products }: { products: MatchedProduct[] }) {
  if (!products.length) {
    return <Chip size="small" variant="outlined" label="0 products" />;
  }
  const preview = products.slice(0, 5).map(productDisplayLabel).join(' · ');
  const suffix = products.length > 5 ? ` … +${products.length - 5} more` : '';
  return (
    <Tooltip title={`${preview}${suffix}`}>
      <Chip
        size="small"
        variant="outlined"
        label={`${products.length} product${products.length === 1 ? '' : 's'}`}
        data-testid="matched-products-count-chip"
      />
    </Tooltip>
  );
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
              {customerDisplayLabel(proposal)}
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
                <TableCell align="right">Pipeline</TableCell>
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
                <TableCell align="right">{fmtUnits(proposal.total_open_order_units ?? 0)}</TableCell>
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
                    <TableCell align="right">Pipeline</TableCell>
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
                      <TableCell align="right">{fmtUnits(m.open_order_units ?? 0)}</TableCell>
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

function BulkLinkConfirmDialog({
  open,
  totalCount,
  byCustomer,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  open: boolean;
  totalCount: number;
  byCustomer: { label: string; count: number }[];
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}) {
  const breakdown =
    byCustomer.map((c) => `${c.label} ${c.count}`).join(', ') || '—';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="po-auto-link-bulk-confirm-dialog">
      <DialogTitle>Confirm bulk link</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" data-testid="po-auto-link-bulk-confirm-summary">
            Linking {totalCount} proposal{totalCount === 1 ? '' : 's'}: {breakdown}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Each selected PO will be linked to its lineup case and the case status set to PO issued.
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
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
          onClick={onConfirm}
          data-testid="po-auto-link-bulk-confirm-submit"
        >
          {isPending ? 'Linking…' : `Link ${totalCount} proposal${totalCount === 1 ? '' : 's'}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function CoverageLine({
  planUnits,
  proposedShipUnits,
  proposedPipelineUnits,
  linkedShipUnits,
}: {
  planUnits: number;
  proposedShipUnits: number;
  proposedPipelineUnits: number;
  linkedShipUnits: number;
}) {
  const overPlan =
    proposedShipUnits > planUnits && planUnits > 0 && proposedPipelineUnits === 0;
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography variant="body2" color="text.secondary" data-testid="po-auto-link-coverage-line" component="span">
        {formatCoverageLineParts({
          planUnits,
          proposedShipUnits,
          proposedPipelineUnits,
          linkedShipUnits,
        })}
      </Typography>
      {proposedPipelineUnits > 0 ? (
        <Chip
          size="small"
          label="pipeline"
          variant="outlined"
          color="info"
          sx={{ height: 20, fontSize: '0.7rem' }}
          data-testid="po-auto-link-pipeline-chip"
        />
      ) : null}
      {overPlan ? (
        <Typography component="span" variant="body2" color="text.secondary">
          (over plan — expected when multiple POs cover the same customer period)
        </Typography>
      ) : null}
    </Stack>
  );
}

function ProposalRow({
  proposal,
  selected,
  onToggleSelect,
  onReview,
  onDismiss,
  onRestore,
  restorePending,
}: {
  proposal: PoAutoLinkProposal;
  selected: boolean;
  onToggleSelect: () => void;
  onReview: () => void;
  onDismiss: () => void;
  onRestore: () => void;
  restorePending: boolean;
}) {
  const dismissed = !!proposal.dismissed;

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1}
      alignItems={{ sm: 'center' }}
      sx={{
        py: 0.75,
        px: 1,
        borderRadius: 1,
        opacity: dismissed ? 0.55 : 1,
        bgcolor: dismissed ? 'action.hover' : 'transparent',
      }}
      data-testid={`po-auto-link-row-${proposal.proposal_key}`}
    >
      <Stack direction="row" spacing={1} alignItems="center" flex={1} flexWrap="wrap" useFlexGap>
        <Checkbox
          size="small"
          checked={selected}
          disabled={dismissed}
          onChange={onToggleSelect}
          inputProps={{ 'data-testid': `po-auto-link-select-${proposal.proposal_key}` } as InputHTMLAttributes<HTMLInputElement>}
        />
        <Tooltip title={reasonLabel(proposal.reason)}>
          <Chip size="small" color={confidenceColor(proposal.confidence)} label={proposal.confidence} />
        </Tooltip>
        <Typography variant="body2" fontWeight={500}>
          {proposal.po_number ?? `#${proposal.purchase_order_id}`}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {[proposal.distributor_code, proposal.distributor_name].filter(Boolean).join(' — ') || '—'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Shipped {fmtUnits(proposal.total_shipped_units)}
          {(proposal.total_open_order_units ?? 0) > 0 ? (
            <>
              {' '}
              <Typography component="span" variant="body2" color="info.main">
                +{fmtUnits(proposal.total_open_order_units)} pipeline
              </Typography>
            </>
          ) : null}
        </Typography>
        <MatchedProductsChip products={proposal.matched_products} />
      </Stack>
      <Stack direction="row" spacing={0.5} flexShrink={0}>
        {dismissed ? (
          <Button size="small" onClick={onRestore} disabled={restorePending} data-testid={`po-auto-link-restore-${proposal.proposal_key}`}>
            Restore
          </Button>
        ) : (
          <>
            <Button size="small" onClick={onReview} data-testid={`po-auto-link-review-${proposal.proposal_key}`}>
              Review
            </Button>
            <Button size="small" color="warning" onClick={onDismiss}>
              Dismiss
            </Button>
          </>
        )}
      </Stack>
    </Stack>
  );
}

function ProposalGroupCard({
  group,
  expanded,
  onToggleExpanded,
  selected,
  onToggleProposal,
  onSelectAllInCard,
  onLinkSelectedInCard,
  onReview,
  onDismiss,
  onRestore,
  restorePending,
  applyPending,
}: {
  group: PoAutoLinkProposalGroup;
  expanded: boolean;
  onToggleExpanded: () => void;
  selected: Set<string>;
  onToggleProposal: (key: string) => void;
  onSelectAllInCard: (keys: string[]) => void;
  onLinkSelectedInCard: (keys: string[]) => void;
  onReview: (p: PoAutoLinkProposal) => void;
  onDismiss: (p: PoAutoLinkProposal) => void;
  onRestore: (key: string) => void;
  restorePending: boolean;
  applyPending: boolean;
}) {
  const selectable = group.proposals.filter((p) => !p.dismissed);
  const selectedInCard = selectable.filter((p) => selected.has(p.proposal_key));
  const allSelected = selectable.length > 0 && selectedInCard.length === selectable.length;
  const someSelected = selectedInCard.length > 0 && !allSelected;
  const periodLabel = group.case_period_label ?? group.inferred_period_start ?? '—';
  const customerLabel = customerDisplayLabel(group.proposals[0]);

  return (
    <Card variant="outlined" data-testid={`po-auto-link-group-card-${group.groupKey}`}>
      <CardContent sx={{ pb: expanded ? 2 : '16px !important' }}>
        <Stack spacing={1}>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            alignItems={{ md: 'center' }}
            justifyContent="space-between"
          >
            <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap sx={{ flex: 1 }}>
              <IconButton size="small" onClick={onToggleExpanded} aria-label={expanded ? 'Collapse card' : 'Expand card'}>
                {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
              </IconButton>
              <Chip size="small" label={periodLabel} />
              <Typography
                variant="subtitle1"
                fontWeight={600}
                sx={{ whiteSpace: 'normal', wordBreak: 'break-word', maxWidth: '100%' }}
                data-testid={`po-auto-link-group-customer-${group.groupKey}`}
              >
                {customerLabel}
              </Typography>
            </Stack>
            <Chip
              size="small"
              variant="outlined"
              label={`${selectedInCard.length} of ${selectable.length} selected`}
              data-testid={`po-auto-link-group-selection-${group.groupKey}`}
            />
          </Stack>

          <Box sx={{ pl: { xs: 0, sm: 5 } }}>
            <Typography variant="body2" color="text.secondary">
              Period plan (customer-scoped): {fmtUnits(group.groupPlanUnits)}
            </Typography>
            <CoverageLine
              planUnits={group.groupPlanUnits}
              proposedShipUnits={group.proposedShipUnits}
              proposedPipelineUnits={group.proposedPipelineUnits}
              linkedShipUnits={group.linkedShipUnits}
            />
          </Box>

          {!expanded && (
            <Typography variant="caption" color="text.secondary" sx={{ pl: { xs: 0, sm: 5 } }}>
              {group.proposals.length} proposal{group.proposals.length === 1 ? '' : 's'} · expand to review rows
            </Typography>
          )}

          <Collapse in={expanded}>
            <Divider sx={{ my: 1 }} />
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={allSelected}
                    indeterminate={someSelected}
                    disabled={!selectable.length}
                    onChange={() => {
                      if (allSelected) onSelectAllInCard([]);
                      else onSelectAllInCard(selectable.map((p) => p.proposal_key));
                    }}
                    inputProps={
                      { 'data-testid': `po-auto-link-card-select-all-${group.groupKey}` } as InputHTMLAttributes<HTMLInputElement>
                    }
                  />
                }
                label="Select all in card"
              />
              <Button
                size="small"
                variant="contained"
                disabled={!selectedInCard.length || applyPending}
                onClick={() => onLinkSelectedInCard(selectedInCard.map((p) => p.proposal_key))}
                data-testid={`po-auto-link-card-link-${group.groupKey}`}
              >
                Link selected ({selectedInCard.length})
              </Button>
            </Stack>
            <Stack spacing={0.5} divider={<Divider flexItem />}>
              {group.proposals.map((p) => (
                <ProposalRow
                  key={p.proposal_key}
                  proposal={p}
                  selected={selected.has(p.proposal_key)}
                  onToggleSelect={() => onToggleProposal(p.proposal_key)}
                  onReview={() => onReview(p)}
                  onDismiss={() => onDismiss(p)}
                  onRestore={() => onRestore(p.proposal_key)}
                  restorePending={restorePending}
                />
              ))}
            </Stack>
          </Collapse>
        </Stack>
      </CardContent>
    </Card>
  );
}

export const PO_AUTO_LINK_SECTION_ID = 'po-auto-link-section';

type PoAutoLinkProposalsSectionProps = {
  /** Prefetch proposals on mount and auto-expand when pending count &gt; 0. */
  autoFetch?: boolean;
  onPendingCountChange?: (count: number) => void;
};

export function PoAutoLinkProposalsSection({
  autoFetch = false,
  onPendingCountChange,
}: PoAutoLinkProposalsSectionProps) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const manualCollapseRef = useRef(false);
  const [period, setPeriod] = useState(() => currentQuarterLabel());
  const [confidence, setConfidence] = useState<'all' | 'high' | 'medium'>('all');
  const [customerFilter, setCustomerFilter] = useState('');
  const [showDismissed, setShowDismissed] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmProposal, setConfirmProposal] = useState<PoAutoLinkProposal | null>(null);
  const [bulkConfirmKeys, setBulkConfirmKeys] = useState<string[] | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [dismissTarget, setDismissTarget] = useState<PoAutoLinkProposal | null>(null);
  const [cardExpanded, setCardExpanded] = useState<Record<string, boolean>>({});

  const queryKey = ['po-auto-link', period, confidence, showDismissed] as const;

  const proposalsQ = useQuery({
    queryKey,
    enabled: expanded || autoFetch,
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
      setBulkConfirmKeys(null);
      setSelected(new Set());
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
  const activeProposals = useMemo(
    () => (showDismissed ? proposals : proposals.filter((p) => !p.dismissed)),
    [proposals, showDismissed]
  );

  const filteredProposals = useMemo(() => {
    const q = customerFilter.trim().toLowerCase();
    if (!q) return activeProposals;
    return activeProposals.filter((p) => {
      const label = (p.customer_label ?? '').toLowerCase();
      const idToken = p.customer_id != null ? String(p.customer_id) : '';
      return label.includes(q) || idToken.includes(q);
    });
  }, [activeProposals, customerFilter]);

  const proposalGroups = useMemo(
    () => buildProposalGroups(filteredProposals, proposalsQ.data?.group_coverage_by_key),
    [filteredProposals, proposalsQ.data?.group_coverage_by_key],
  );

  const proposalByKey = useMemo(() => {
    const map = new Map<string, PoAutoLinkProposal>();
    for (const p of filteredProposals) map.set(p.proposal_key, p);
    return map;
  }, [filteredProposals]);

  useEffect(() => {
    if (!proposalGroups.length) return;
    const defaultExpanded = proposalGroups.length <= 3;
    setCardExpanded((prev) => {
      const next = { ...prev };
      for (const g of proposalGroups) {
        if (!(g.groupKey in next)) next[g.groupKey] = defaultExpanded;
      }
      return next;
    });
  }, [proposalGroups]);

  const pendingCount = Math.max(0, (proposalsQ.data?.total ?? 0) - (proposalsQ.data?.dismissed_count ?? 0));

  useEffect(() => {
    if (!autoFetch) return;
    onPendingCountChange?.(pendingCount);
    if (pendingCount > 0 && !manualCollapseRef.current) {
      setExpanded(true);
    }
  }, [autoFetch, onPendingCountChange, pendingCount]);

  const handleExpand = useCallback(() => {
    manualCollapseRef.current = false;
    setExpanded(true);
  }, []);

  const handleCollapse = useCallback(() => {
    manualCollapseRef.current = true;
    setExpanded(false);
  }, []);

  const toggleProposalSelection = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const replaceCardSelection = useCallback((groupKey: string, keys: string[]) => {
    const group = proposalGroups.find((g) => g.groupKey === groupKey);
    if (!group) return;
    const groupKeys = new Set(group.proposals.map((p) => p.proposal_key));
    setSelected((prev) => {
      const next = new Set([...prev].filter((k) => !groupKeys.has(k)));
      for (const k of keys) next.add(k);
      return next;
    });
  }, [proposalGroups]);

  const selectAllHigh = () => {
    const keys = filteredProposals.filter((p) => p.confidence === 'high' && !p.dismissed).map((p) => p.proposal_key);
    setSelected(new Set(keys));
  };

  const openBulkConfirm = (keys: string[]) => {
    if (!keys.length) return;
    setApplyError(null);
    setBulkConfirmKeys(keys);
  };

  const bulkConfirmBreakdown = useMemo(() => {
    if (!bulkConfirmKeys?.length) return [];
    const counts = new Map<string, number>();
    for (const key of bulkConfirmKeys) {
      const p = proposalByKey.get(key);
      const label = p ? customerDisplayLabel(p) : key;
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [bulkConfirmKeys, proposalByKey]);

  const executeBulkApply = () => {
    if (!bulkConfirmKeys?.length) return;
    const items = bulkConfirmKeys
      .map((key) => proposalByKey.get(key))
      .filter((p): p is PoAutoLinkProposal => !!p && !p.dismissed)
      .map((p) => ({ case_id: p.case_id, purchase_order_id: p.purchase_order_id }));
    if (!items.length) return;
    setApplyError(null);
    applyMut.mutate({ items });
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

  return (
    <Card variant="outlined" id={PO_AUTO_LINK_SECTION_ID} data-testid="po-auto-link-section">
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
              <Button variant="contained" size="small" onClick={handleExpand} data-testid="po-auto-link-expand">
                {autoFetch && proposalsQ.isFetching
                  ? 'Loading suggestions…'
                  : pendingCount > 0
                    ? `Show ${pendingCount} suggestion${pendingCount === 1 ? '' : 's'}`
                    : 'Compute / show suggested links'}
              </Button>
            ) : (
              <Button size="small" variant="outlined" onClick={handleCollapse} data-testid="po-auto-link-collapse">
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
                <TextField
                  size="small"
                  label="Customer filter"
                  placeholder="Name or customer id"
                  value={customerFilter}
                  onChange={(e) => setCustomerFilter(e.target.value)}
                  sx={{ minWidth: 160 }}
                  data-testid="po-auto-link-customer"
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
                <Button size="small" onClick={selectAllHigh} disabled={!filteredProposals.some((p) => p.confidence === 'high')}>
                  Select all high
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  disabled={selected.size === 0 || applyMut.isPending}
                  onClick={() => openBulkConfirm([...selected])}
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
              ) : !filteredProposals.length && !showDismissed ? (
                <Alert severity="info" data-testid="po-auto-link-empty">
                  No link proposals for the current filters. Try clearing the period or customer filter or lowering confidence.
                </Alert>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary">
                    Showing {filteredProposals.length} of {proposalsQ.data?.total ?? 0} proposals
                    {customerFilter.trim() && activeProposals.length !== filteredProposals.length
                      ? ` (${activeProposals.length} before customer filter)`
                      : ''}
                    {(proposalsQ.data?.dismissed_count ?? 0) > 0
                      ? ` · ${proposalsQ.data?.dismissed_count} dismissed`
                      : ''}
                  </Typography>
                  <Stack spacing={1.5} data-testid="po-auto-link-cards">
                    {proposalGroups.map((group) => (
                      <ProposalGroupCard
                        key={group.groupKey}
                        group={group}
                        expanded={cardExpanded[group.groupKey] ?? proposalGroups.length <= 3}
                        onToggleExpanded={() =>
                          setCardExpanded((prev) => ({
                            ...prev,
                            [group.groupKey]: !(prev[group.groupKey] ?? proposalGroups.length <= 3),
                          }))
                        }
                        selected={selected}
                        onToggleProposal={toggleProposalSelection}
                        onSelectAllInCard={(keys) => replaceCardSelection(group.groupKey, keys)}
                        onLinkSelectedInCard={openBulkConfirm}
                        onReview={(p) => {
                          setApplyError(null);
                          setConfirmProposal(p);
                        }}
                        onDismiss={setDismissTarget}
                        onRestore={(key) => restoreMut.mutate(key)}
                        restorePending={restoreMut.isPending}
                        applyPending={applyMut.isPending}
                      />
                    ))}
                  </Stack>
                </>
              )}

              {applyError && !confirmProposal && !bulkConfirmKeys && <Alert severity="error">{applyError}</Alert>}
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

      <BulkLinkConfirmDialog
        open={!!bulkConfirmKeys?.length}
        totalCount={bulkConfirmKeys?.length ?? 0}
        byCustomer={bulkConfirmBreakdown}
        onClose={() => {
          setBulkConfirmKeys(null);
          setApplyError(null);
        }}
        onConfirm={executeBulkApply}
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

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
  LinearProgress,
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
import {
  ResolutionWorklist,
  type WorkItemProtection,
} from '@/features/steward-worklist';

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

export type BulkProtection = {
  selection_protected: boolean;
  requires_allow_protected: boolean;
  reasons: string[];
  contested: boolean;
};

export type PoAutoLinkCompetition = {
  status: string;
  reason?: string | null;
  competing_case_ids?: number[];
  blocks_apply?: boolean;
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
  commercial_status?: string | null;
  po_link_count?: number;
  competition?: PoAutoLinkCompetition | null;
  bulk_protection?: BulkProtection | null;
};

function protectionReasonLabels(p: PoAutoLinkProposal): string[] {
  const labels: string[] = [];
  const reasons = p.bulk_protection?.reasons ?? [];
  for (const r of reasons) {
    if (r === 'status_advanced') labels.push(`status ${p.commercial_status ?? 'advanced'}`);
    else if (r === 'confirmed_po_links') labels.push(`has ${p.po_link_count ?? '?'} PO link(s)`);
    else if (r === 'tenant_protected_id') labels.push('tenant-protected case id');
    else labels.push(r);
  }
  if (p.bulk_protection?.contested || p.competition?.status === 'contested') {
    labels.push('contested PO');
  }
  return labels;
}

function isSelectionProtected(p: PoAutoLinkProposal): boolean {
  return Boolean(p.bulk_protection?.selection_protected);
}

function requiresAllowProtected(p: PoAutoLinkProposal): boolean {
  return Boolean(p.bulk_protection?.requires_allow_protected);
}

function isContested(p: PoAutoLinkProposal): boolean {
  return Boolean(p.bulk_protection?.contested || p.competition?.status === 'contested');
}

function toWorkItemProtection(p: PoAutoLinkProposal): WorkItemProtection | null {
  const bp = p.bulk_protection;
  const contested = isContested(p);
  if (!bp && !contested) return null;
  return {
    selectionProtected: Boolean(bp?.selection_protected || contested),
    requiresOverride: Boolean(bp?.requires_allow_protected),
    contested,
    reasonLabels: protectionReasonLabels(p),
  };
}

type PoAutoLinkBucketId = 'all' | 'contested' | 'clean' | 'high' | 'medium';

function matchesBucket(p: PoAutoLinkProposal, bucket: PoAutoLinkBucketId): boolean {
  if (bucket === 'all') return true;
  if (bucket === 'high') return p.confidence === 'high';
  if (bucket === 'medium') return p.confidence === 'medium';
  if (bucket === 'contested') return isContested(p);
  if (bucket === 'clean') return !isContested(p);
  return true;
}

function proposalGroupKey(p: PoAutoLinkProposal): string {
  const period = p.case_period_label ?? p.inferred_period_start ?? '';
  return `${period}|${p.customer_id ?? 'null'}`;
}

type GroupCoverageEntry = {
  group_key: string;
  linked_shipped_units: number;
  group_planned_units?: number;
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
    const key = proposalGroupKey(p);
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
        groupPlanUnits:
          coverageByKey?.[groupKey]?.group_planned_units ?? dedupeGroupPlanUnits(bucket),
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
  onConfirm: (notes: string, allowProtected: boolean) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [notes, setNotes] = useState('');
  const [allowProtected, setAllowProtected] = useState(false);

  if (!proposal) return null;

  const needsOverride = requiresAllowProtected(proposal);
  const protectionLabels = protectionReasonLabels(proposal);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="po-auto-link-confirm-dialog">
      <DialogTitle>Link PO to lineup case</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            This links the observed purchase order to the lineup case and sets the case to{' '}
            <strong>PO linked</strong>. Review customer and product overlap before confirming.
          </Typography>
          {protectionLabels.length > 0 ? (
            <Alert
              severity={needsOverride ? 'warning' : 'info'}
              data-testid="po-auto-link-confirm-protection"
            >
              Protected from bulk automation: {protectionLabels.join('; ')}.
              {needsOverride
                ? ' Deliberate override required to link.'
                : ' Contested items stay linkable individually (FLAG≠BLOCK).'}
            </Alert>
          ) : null}
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
            {proposal.commercial_status ? (
              <Chip size="small" variant="outlined" label={proposal.commercial_status} />
            ) : null}
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
          {needsOverride ? (
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={allowProtected}
                  onChange={(e) => setAllowProtected(e.target.checked)}
                  inputProps={
                    { 'data-testid': 'po-auto-link-allow-protected' } as InputHTMLAttributes<HTMLInputElement>
                  }
                />
              }
              label="Allow linking this protected case (deliberate override)"
            />
          ) : null}
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
          disabled={isPending || (needsOverride && !allowProtected)}
          onClick={() => onConfirm(notes, allowProtected)}
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
  excluded,
  onClose,
  onConfirm,
  isPending,
  error,
  progress,
}: {
  open: boolean;
  totalCount: number;
  byCustomer: { label: string; count: number }[];
  excluded: { label: string; reasons: string }[];
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
  progress?: PoAutoLinkApplyProgress | null;
}) {
  const breakdown =
    byCustomer.map((c) => `${c.label} ${c.count}`).join(', ') || '—';

  return (
    <Dialog
      open={open}
      onClose={isPending ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      data-testid="po-auto-link-bulk-confirm-dialog"
    >
      <DialogTitle>Confirm bulk link</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" data-testid="po-auto-link-bulk-confirm-summary">
            Linking {totalCount} proposal{totalCount === 1 ? '' : 's'}: {breakdown}
          </Typography>
          {excluded.length > 0 ? (
            <Alert severity="warning" data-testid="po-auto-link-bulk-excluded">
              Excluded from bulk ({excluded.length}):{' '}
              {excluded.map((e) => `${e.label} (${e.reasons})`).join('; ')}
            </Alert>
          ) : null}
          {!isPending ? (
            <Typography variant="body2" color="text.secondary">
              Each selected PO will be linked to its lineup case (status advances to PO linked; steward work stays open).
              Protected / contested cases stay out of select-all; override is single-item only.
            </Typography>
          ) : null}
          {isPending && progress ? (
            <Box>
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                {progress.itemsDone} / {progress.itemsTotal} processed
                {progress.batchTotal > 1 ? ` · batch ${progress.batchIndex} of ${progress.batchTotal}` : ''}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={progress.itemsTotal > 0 ? (progress.itemsDone / progress.itemsTotal) * 100 : 0}
              />
            </Box>
          ) : null}
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
          disabled={isPending || totalCount === 0}
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

function CompetitionChip({ proposal }: { proposal: PoAutoLinkProposal }) {
  const comp = proposal.competition;
  if (!comp?.status || comp.status === 'not_contested') return null;
  const label =
    comp.status === 'contested'
      ? 'Competition: contested'
      : comp.status === 'indeterminate'
        ? 'Competition: indeterminate'
        : `Competition: ${comp.status}`;
  return (
    <Tooltip title={comp.reason ?? label}>
      <Chip size="small" variant="outlined" color="warning" label={label} />
    </Tooltip>
  );
}

function PoAutoLinkProposalRowContent({
  proposal,
  onReview,
  onDismiss,
  onRestore,
  restorePending,
}: {
  proposal: PoAutoLinkProposal;
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
        flex: 1,
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" flex={1} flexWrap="wrap" useFlexGap>
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
        <CompetitionChip proposal={proposal} />
        {isSelectionProtected(proposal) ? (
          <Tooltip title={protectionReasonLabels(proposal).join('; ') || 'Protected'}>
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label={
                requiresAllowProtected(proposal)
                  ? 'Protected'
                  : proposal.competition?.status === 'contested'
                    ? 'Contested'
                    : 'Protected'
              }
              data-testid={`po-auto-link-protected-${proposal.proposal_key}`}
            />
          </Tooltip>
        ) : null}
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

function PoAutoLinkGroupHeader({
  group,
  expanded,
  onToggleExpanded,
  selected,
  onSelectAllInCard,
  onLinkSelectedInCard,
  applyPending,
}: {
  group: PoAutoLinkProposalGroup;
  expanded: boolean;
  onToggleExpanded: () => void;
  selected: Set<string>;
  onSelectAllInCard: (keys: string[]) => void;
  onLinkSelectedInCard: (keys: string[]) => void;
  applyPending: boolean;
}) {
  const autoSelectable = group.proposals.filter((p) => !p.dismissed && !isSelectionProtected(p));
  const selectedInCard = group.proposals.filter((p) => !p.dismissed && selected.has(p.proposal_key));
  const selectedLinkable = selectedInCard.filter((p) => !requiresAllowProtected(p));
  const allSelected = autoSelectable.length > 0 && autoSelectable.every((p) => selected.has(p.proposal_key));
  const someSelected =
    autoSelectable.some((p) => selected.has(p.proposal_key)) && !allSelected;
  const protectedInCard = group.proposals.filter((p) => !p.dismissed && isSelectionProtected(p));
  const periodLabel = group.case_period_label ?? group.inferred_period_start ?? '—';
  const customerLabel = customerDisplayLabel(group.proposals[0]);

  return (
    <Card variant="outlined" data-testid={`po-auto-link-group-card-${group.groupKey}`} sx={{ mb: 1 }}>
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
              label={`${selectedInCard.length} of ${group.proposals.filter((p) => !p.dismissed).length} selected`}
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
                    disabled={!autoSelectable.length}
                    onChange={() => {
                      if (allSelected) onSelectAllInCard([]);
                      else onSelectAllInCard(autoSelectable.map((p) => p.proposal_key));
                    }}
                    inputProps={
                      { 'data-testid': `po-auto-link-card-select-all-${group.groupKey}` } as InputHTMLAttributes<HTMLInputElement>
                    }
                  />
                }
                label="Select all in card"
              />
              {protectedInCard.length > 0 ? (
                <Typography
                  variant="caption"
                  color="warning.main"
                  data-testid={`po-auto-link-card-excluded-${group.groupKey}`}
                >
                  {protectedInCard.length} excluded from select-all (protected/contested — select individually)
                </Typography>
              ) : null}
              <Button
                size="small"
                variant="contained"
                disabled={!selectedLinkable.length || applyPending}
                onClick={() => onLinkSelectedInCard(selectedLinkable.map((p) => p.proposal_key))}
                data-testid={`po-auto-link-card-link-${group.groupKey}`}
              >
                Link selected ({selectedLinkable.length})
              </Button>
            </Stack>
          </Collapse>
        </Stack>
      </CardContent>
    </Card>
  );
}

const PO_AUTO_LINK_APPLY_CHUNK = 100;

type PoAutoLinkApplyResponse = {
  applied_count?: number;
  error_count?: number;
  errors?: { error: string }[];
  applied?: { newly_linked?: boolean }[];
};

type PoAutoLinkApplyProgress = {
  itemsDone: number;
  itemsTotal: number;
  batchIndex: number;
  batchTotal: number;
};

async function applyPoAutoLinkInChunks(
  items: { case_id: number; purchase_order_id: number; notes?: string; allow_protected?: boolean }[],
  notes?: string,
  onProgress?: (progress: PoAutoLinkApplyProgress) => void,
): Promise<PoAutoLinkApplyResponse & { newly_linked_count: number }> {
  let applied_count = 0;
  let newly_linked_count = 0;
  let error_count = 0;
  const errors: { error: string }[] = [];
  const batchTotal = Math.max(1, Math.ceil(items.length / PO_AUTO_LINK_APPLY_CHUNK));
  onProgress?.({ itemsDone: 0, itemsTotal: items.length, batchIndex: 0, batchTotal });

  for (let i = 0; i < items.length; i += PO_AUTO_LINK_APPLY_CHUNK) {
    const batchIndex = Math.floor(i / PO_AUTO_LINK_APPLY_CHUNK) + 1;
    const chunk = items.slice(i, i + PO_AUTO_LINK_APPLY_CHUNK);
    onProgress?.({
      itemsDone: i,
      itemsTotal: items.length,
      batchIndex,
      batchTotal,
    });
    const data = await apiPost<PoAutoLinkApplyResponse>(
      '/api/v1/commercial-planner/lineup/po-auto-link/apply',
      { items: chunk, notes },
    );
    applied_count += data.applied_count ?? 0;
    newly_linked_count += (data.applied ?? []).filter((row) => row.newly_linked).length;
    error_count += data.error_count ?? 0;
    if (data.errors?.length) errors.push(...data.errors);
    onProgress?.({
      itemsDone: Math.min(i + chunk.length, items.length),
      itemsTotal: items.length,
      batchIndex,
      batchTotal,
    });
  }
  return { applied_count, newly_linked_count, error_count, errors };
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
  const [period, setPeriod] = useState('');
  const [confidence, setConfidence] = useState<'all' | 'high' | 'medium'>('all');
  const [customerFilter, setCustomerFilter] = useState('');
  const [debouncedCustomer, setDebouncedCustomer] = useState('');
  const [bucket, setBucket] = useState<PoAutoLinkBucketId>('all');
  const [showDismissed, setShowDismissed] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drawerKey, setDrawerKey] = useState<string | null>(null);
  const [confirmProposal, setConfirmProposal] = useState<PoAutoLinkProposal | null>(null);
  const [bulkConfirmKeys, setBulkConfirmKeys] = useState<string[] | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applySuccess, setApplySuccess] = useState<string | null>(null);
  const [applyProgress, setApplyProgress] = useState<PoAutoLinkApplyProgress | null>(null);
  const [dismissTarget, setDismissTarget] = useState<PoAutoLinkProposal | null>(null);
  const [cardExpanded, setCardExpanded] = useState<Record<string, boolean>>({});
  const [manualCaseId, setManualCaseId] = useState('');
  const [manualPoNumber, setManualPoNumber] = useState('');
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualPending, setManualPending] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedCustomer(customerFilter), 300);
    return () => window.clearTimeout(handle);
  }, [customerFilter]);

  const filtersAtDefault =
    period === '' && confidence === 'all' && customerFilter === '' && bucket === 'all';

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
    mutationFn: (vars: { items: { case_id: number; purchase_order_id: number; notes?: string; allow_protected?: boolean }[]; notes?: string }) =>
      applyPoAutoLinkInChunks(vars.items, vars.notes, setApplyProgress),
    onSuccess: (data: {
      applied_count?: number;
      newly_linked_count?: number;
      error_count?: number;
      errors?: { error: string }[];
    }) => {
      const applied = data.applied_count ?? 0;
      const newly = data.newly_linked_count ?? 0;
      const skipped = Math.max(0, applied - newly);
      if (data.error_count) {
        setApplyError(
          data.errors?.map((e) => e.error).join('; ') ?? `${data.error_count} link(s) failed`,
        );
      } else {
        setApplyError(null);
      }
      if (applied > 0) {
        const parts = [`${newly} new PO link${newly === 1 ? '' : 's'} created`];
        if (skipped > 0) parts.push(`${skipped} already linked`);
        if (data.error_count) parts.push(`${data.error_count} failed`);
        setApplySuccess(`Bulk link complete: ${parts.join(' · ')}. Refreshing suggestions…`);
      } else if (!data.error_count) {
        setApplySuccess('Bulk link finished — no changes (all selected proposals were already linked).');
      }
      setConfirmProposal(null);
      setDrawerKey(null);
      setBulkConfirmKeys(null);
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
      void qc.invalidateQueries({ queryKey: ['po-management'] });
      void qc.invalidateQueries({ queryKey: ['lineup-cases'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      setApplyProgress(null);
    },
    onError: (e) => {
      setApplyProgress(null);
      setApplySuccess(null);
      setApplyError(safeDisplayError(e));
    },
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
      setDrawerKey(null);
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

  const customerFilteredProposals = useMemo(() => {
    const q = debouncedCustomer.trim().toLowerCase();
    if (!q) return activeProposals;
    return activeProposals.filter((p) => {
      const label = (p.customer_label ?? '').toLowerCase();
      const idToken = p.customer_id != null ? String(p.customer_id) : '';
      return label.includes(q) || idToken.includes(q);
    });
  }, [activeProposals, debouncedCustomer]);

  const bucketFilteredProposals = useMemo(
    () => customerFilteredProposals.filter((p) => matchesBucket(p, bucket)),
    [customerFilteredProposals, bucket],
  );

  const proposalGroups = useMemo(
    () => buildProposalGroups(bucketFilteredProposals, proposalsQ.data?.group_coverage_by_key),
    [bucketFilteredProposals, proposalsQ.data?.group_coverage_by_key],
  );

  const proposalGroupByKey = useMemo(() => {
    const map = new Map<string, PoAutoLinkProposalGroup>();
    for (const g of proposalGroups) map.set(g.groupKey, g);
    return map;
  }, [proposalGroups]);

  const proposalByKey = useMemo(() => {
    const map = new Map<string, PoAutoLinkProposal>();
    for (const p of bucketFilteredProposals) map.set(p.proposal_key, p);
    return map;
  }, [bucketFilteredProposals]);


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

  const bucketCounts = useMemo(
    () => ({
      all: customerFilteredProposals.length,
      contested: customerFilteredProposals.filter((p) => matchesBucket(p, 'contested')).length,
      clean: customerFilteredProposals.filter((p) => matchesBucket(p, 'clean')).length,
      high: customerFilteredProposals.filter((p) => matchesBucket(p, 'high')).length,
      medium: customerFilteredProposals.filter((p) => matchesBucket(p, 'medium')).length,
    }),
    [customerFilteredProposals],
  );

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
    const keys = bucketFilteredProposals
      .filter((p) => p.confidence === 'high' && !p.dismissed && !isSelectionProtected(p))
      .map((p) => p.proposal_key);
    setSelected(new Set(keys));
  };

  const clearFiltersToDefault = () => {
    setPeriod('');
    setConfidence('all');
    setCustomerFilter('');
    setDebouncedCustomer('');
    setBucket('all');
    setSelected(new Set());
  };

  const handleBucketChange = (id: PoAutoLinkBucketId) => {
    setBucket(id);
    setSelected(new Set());
  };

  const openBulkConfirm = (keys: string[]) => {
    if (!keys.length) return;
    setApplyError(null);
    setBulkConfirmKeys(keys);
  };

  const bulkConfirmPartition = useMemo(() => {
    if (!bulkConfirmKeys?.length) {
      return { linkable: [] as PoAutoLinkProposal[], excluded: [] as PoAutoLinkProposal[] };
    }
    const linkable: PoAutoLinkProposal[] = [];
    const excluded: PoAutoLinkProposal[] = [];
    for (const key of bulkConfirmKeys) {
      const p = proposalByKey.get(key);
      if (!p || p.dismissed) continue;
      if (requiresAllowProtected(p)) excluded.push(p);
      else linkable.push(p);
    }
    return { linkable, excluded };
  }, [bulkConfirmKeys, proposalByKey]);

  const bulkConfirmBreakdown = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of bulkConfirmPartition.linkable) {
      const label = customerDisplayLabel(p);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [bulkConfirmPartition]);

  const bulkExcludedRows = useMemo(
    () =>
      bulkConfirmPartition.excluded.map((p) => ({
        label: `${customerDisplayLabel(p)} case ${p.case_id} PO ${p.po_number ?? p.purchase_order_id}`,
        reasons: protectionReasonLabels(p).join(', ') || 'protected',
      })),
    [bulkConfirmPartition]
  );

  const executeBulkApply = () => {
    const items = bulkConfirmPartition.linkable.map((p) => ({
      case_id: p.case_id,
      purchase_order_id: p.purchase_order_id,
    }));
    if (!items.length) return;
    setApplyError(null);
    setApplySuccess(null);
    applyMut.mutate({ items });
  };

  const handleSingleConfirm = (notes: string, allowProtected: boolean) => {
    if (!confirmProposal) return;
    setApplyError(null);
    applyMut.mutate({
      items: [
        {
          case_id: confirmProposal.case_id,
          purchase_order_id: confirmProposal.purchase_order_id,
          notes: notes.trim() || undefined,
          ...(allowProtected ? { allow_protected: true } : {}),
        },
      ],
    });
  };

  const handleManualLink = async () => {
    setManualError(null);
    const caseId = Number.parseInt(manualCaseId.trim(), 10);
    if (!Number.isFinite(caseId) || caseId < 1) {
      setManualError('Enter a valid case id');
      return;
    }
    if (!manualPoNumber.trim()) {
      setManualError('Enter an exact PO number');
      return;
    }
    setManualPending(true);
    try {
      const po = await apiGet<{
        purchase_order_id: number;
        po_number: string;
        po_number_norm: string;
      }>(
        `/api/v1/commercial-planner/lineup/po-auto-link/exact-po?po_number=${encodeURIComponent(manualPoNumber.trim())}`,
      );
      await applyPoAutoLinkInChunks(
        [{ case_id: caseId, purchase_order_id: po.purchase_order_id }],
        undefined,
        setApplyProgress,
      );
      setManualCaseId('');
      setManualPoNumber('');
      setApplySuccess(`Manual link applied for case ${caseId} ↔ ${po.po_number}.`);
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
      void qc.invalidateQueries({ queryKey: ['po-management'] });
      void qc.invalidateQueries({ queryKey: ['lineup-cases'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      setApplyProgress(null);
    } catch (e) {
      setManualError(safeDisplayError(e));
      setApplyProgress(null);
    } finally {
      setManualPending(false);
    }
  };

  const isGroupExpanded = (groupKey: string) =>
    cardExpanded[groupKey] ?? proposalGroups.length <= 3;

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

          {(applyMut.isPending || applyProgress || manualPending) && (
            <Box data-testid="po-auto-link-apply-progress">
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                <Typography variant="body2">
                  Linking proposals…{' '}
                  {applyProgress
                    ? `${applyProgress.itemsDone} / ${applyProgress.itemsTotal}`
                    : 'starting…'}
                </Typography>
                {applyProgress && applyProgress.batchTotal > 1 ? (
                  <Typography variant="caption" color="text.secondary">
                    Batch {applyProgress.batchIndex} of {applyProgress.batchTotal}
                  </Typography>
                ) : null}
              </Stack>
              <LinearProgress
                variant={applyProgress ? 'determinate' : 'indeterminate'}
                value={
                  applyProgress && applyProgress.itemsTotal > 0
                    ? (applyProgress.itemsDone / applyProgress.itemsTotal) * 100
                    : 0
                }
              />
            </Box>
          )}

          {applySuccess && !confirmProposal && !bulkConfirmKeys && (
            <Alert
              severity="success"
              data-testid="po-auto-link-apply-success"
              onClose={() => setApplySuccess(null)}
            >
              {applySuccess}
            </Alert>
          )}
          {applyError && !confirmProposal && !bulkConfirmKeys && (
            <Alert severity="error" data-testid="po-auto-link-apply-error" onClose={() => setApplyError(null)}>
              {applyError}
            </Alert>
          )}

          <Collapse in={expanded}>
            <Stack spacing={2}>
              {proposalsQ.isLoading ? (
                <Typography variant="body2" color="text.secondary" data-testid="po-auto-link-loading">
                  Computing proposals…
                </Typography>
              ) : proposalsQ.data?.data_unavailable ? (
                <Alert severity="info">Auto-link proposals are temporarily unavailable.</Alert>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary">
                    Showing {bucketFilteredProposals.length} of {proposalsQ.data?.total ?? 0} proposals
                    {debouncedCustomer.trim() && activeProposals.length !== bucketFilteredProposals.length
                      ? ` (${activeProposals.length} before customer/bucket filter)`
                      : ''}
                    {(proposalsQ.data?.dismissed_count ?? 0) > 0
                      ? ` · ${proposalsQ.data?.dismissed_count} dismissed`
                      : ''}
                  </Typography>
                  {!bucketFilteredProposals.length && !showDismissed ? (
                    <Alert severity="info" data-testid="po-auto-link-empty">
                      No link proposals for the current filters. Try clearing the period or customer filter or lowering confidence.
                    </Alert>
                  ) : null}
                  <Box data-testid="po-auto-link-cards">
                    <ResolutionWorklist<PoAutoLinkProposal, PoAutoLinkBucketId>
                      rootTestId="po-auto-link"
                      getCheckboxTestId={(k) => `po-auto-link-select-${k}`}
                      bordered
                      items={bucketFilteredProposals}
                      getItemKey={(p) => p.proposal_key}
                      getProtection={toWorkItemProtection}
                      buckets={[
                        { id: 'all', label: 'All', count: bucketCounts.all },
                        { id: 'contested', label: 'Contested', count: bucketCounts.contested },
                        { id: 'clean', label: 'Clean', count: bucketCounts.clean },
                        { id: 'high', label: 'High', count: bucketCounts.high },
                        { id: 'medium', label: 'Medium', count: bucketCounts.medium },
                      ]}
                      activeBucket={bucket}
                      onBucketChange={handleBucketChange}
                      groupBy={proposalGroupKey}
                      isGroupCollapsed={(groupKey) => !isGroupExpanded(groupKey)}
                      renderGroupHeader={(groupKey) => {
                        const group = proposalGroupByKey.get(groupKey);
                        if (!group) return null;
                        return (
                          <PoAutoLinkGroupHeader
                            group={group}
                            expanded={isGroupExpanded(groupKey)}
                            onToggleExpanded={() =>
                              setCardExpanded((prev) => ({
                                ...prev,
                                [groupKey]: !isGroupExpanded(groupKey),
                              }))
                            }
                            selected={selected}
                            onSelectAllInCard={(keys) => replaceCardSelection(groupKey, keys)}
                            onLinkSelectedInCard={openBulkConfirm}
                            applyPending={applyMut.isPending}
                          />
                        );
                      }}
                      renderRow={(proposal) => (
                        <PoAutoLinkProposalRowContent
                          proposal={proposal}
                          onReview={() => {
                            setApplyError(null);
                            setDrawerKey(proposal.proposal_key);
                          }}
                          onDismiss={() => setDismissTarget(proposal)}
                          onRestore={() => restoreMut.mutate(proposal.proposal_key)}
                          restorePending={restoreMut.isPending}
                        />
                      )}
                      selection={{
                        selected,
                        onToggle: toggleProposalSelection,
                        onReplace: (keys) => setSelected(new Set(keys)),
                      }}
                      renderFilters={() => (
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
                          <TextField
                            size="small"
                            label="Period filter"
                            placeholder="All periods / include residual"
                            value={period}
                            onChange={(e) => setPeriod(e.target.value)}
                            sx={{ minWidth: 180 }}
                            inputProps={{ 'data-testid': 'po-auto-link-period' }}
                          />
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => setPeriod(currentQuarterLabel())}
                            data-testid="po-auto-link-period-this-quarter"
                          >
                            This quarter
                          </Button>
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
                          {!filtersAtDefault ? (
                            <Button size="small" onClick={clearFiltersToDefault} data-testid="po-auto-link-clear-filters">
                              Clear filters
                            </Button>
                          ) : null}
                        </Stack>
                      )}
                      renderToolbar={() => (
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                          <Button size="small" onClick={() => setShowDismissed((v) => !v)} data-testid="po-auto-link-toggle-dismissed">
                            {showDismissed ? 'Hide dismissed' : 'Show dismissed'}
                          </Button>
                          <Button
                            size="small"
                            onClick={selectAllHigh}
                            disabled={!bucketFilteredProposals.some((p) => p.confidence === 'high')}
                          >
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
                      )}
                      renderManualLinkSlot={() => (
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'flex-start' }} flexWrap="wrap" useFlexGap>
                          <TextField
                            size="small"
                            label="Case id"
                            value={manualCaseId}
                            onChange={(e) => setManualCaseId(e.target.value)}
                            sx={{ minWidth: 100 }}
                            inputProps={{ 'data-testid': 'po-auto-link-manual-case-id' }}
                          />
                          <TextField
                            size="small"
                            label="Exact PO number"
                            value={manualPoNumber}
                            onChange={(e) => setManualPoNumber(e.target.value)}
                            sx={{ minWidth: 160 }}
                            inputProps={{ 'data-testid': 'po-auto-link-manual-po-number' }}
                          />
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={manualPending || applyMut.isPending}
                            onClick={() => void handleManualLink()}
                            data-testid="po-auto-link-manual-link-btn"
                          >
                            Manual link
                          </Button>
                          {manualError ? (
                            <Alert severity="error" sx={{ flex: 1 }} data-testid="po-auto-link-manual-error">
                              {manualError}
                            </Alert>
                          ) : null}
                        </Stack>
                      )}
                      drawer={{
                        activeKey: drawerKey,
                        onClose: () => setDrawerKey(null),
                        title: (p) => `PO ${p.po_number ?? p.purchase_order_id} ↔ case ${p.case_id}`,
                        renderEvidence: (p) => (
                          <Stack spacing={1}>
                            <Typography variant="body2">
                              <strong>Case id:</strong> {p.case_id}
                            </Typography>
                            <Typography variant="body2">
                              <strong>Period:</strong> {p.case_period_label ?? p.inferred_period_start ?? '—'}
                            </Typography>
                            <Typography variant="body2">
                              <strong>Distributor:</strong>{' '}
                              {[p.distributor_code, p.distributor_name].filter(Boolean).join(' — ') || '—'}
                            </Typography>
                            <Typography variant="body2">
                              <strong>Reason:</strong> {reasonLabel(p.reason)}
                            </Typography>
                            {p.competition?.competing_case_ids?.length ? (
                              <Typography variant="body2">
                                <strong>Competing case ids:</strong> {p.competition.competing_case_ids.join(', ')}
                              </Typography>
                            ) : null}
                            {p.matched_products.length > 0 ? (
                              <Box>
                                <Typography variant="subtitle2" gutterBottom>
                                  Matched products ({p.matched_products.length})
                                </Typography>
                                <Stack spacing={0.5}>
                                  {p.matched_products.map((m) => (
                                    <Typography key={m.product_id} variant="body2">
                                      {productDisplayLabel(m)} — planned {fmtUnits(m.planned_units)}, shipped{' '}
                                      {fmtUnits(m.shipped_units)}
                                    </Typography>
                                  ))}
                                </Stack>
                              </Box>
                            ) : null}
                          </Stack>
                        ),
                        renderDispositionActions: (p) => (
                          <Stack direction="row" spacing={1}>
                            <Button
                              size="small"
                              variant="contained"
                              onClick={() => {
                                setApplyError(null);
                                setConfirmProposal(p);
                              }}
                              data-testid={`po-auto-link-drawer-link-${p.proposal_key}`}
                            >
                              Link
                            </Button>
                            <Button size="small" color="warning" onClick={() => setDismissTarget(p)}>
                              Dismiss
                            </Button>
                          </Stack>
                        ),
                      }}
                    />
                  </Box>
                </>
              )}
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
        totalCount={bulkConfirmPartition.linkable.length}
        byCustomer={bulkConfirmBreakdown}
        excluded={bulkExcludedRows}
        onClose={() => {
          setBulkConfirmKeys(null);
          setApplyError(null);
        }}
        onConfirm={executeBulkApply}
        isPending={applyMut.isPending}
        progress={applyProgress}
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

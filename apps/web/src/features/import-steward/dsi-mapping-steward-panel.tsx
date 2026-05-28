'use client';

import {
  Alert,
  Box,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

import { notifyDsiAsyncPipelineStarted } from './dsiAsyncPipelineRun';
import { detectSuffixTokenFamily } from './dsiDuplicateCluster';
import { DSI_STEWARD_CONFIG, invalidateDsiImportJobStewardQueries, isDsiStewardRowActionBlocked } from './dsiSteward.config';
import { DsiDuplicatePeerCompare } from './dsiDuplicatePeerCompare';
import { DsiDuplicateClusterSameEntityDialog } from './DsiDuplicateClusterSameEntityDialog';
import { DsiDuplicateSameEntityDialog } from './DsiDuplicateSameEntityDialog';
import {
  classifyDuplicateSameEntityCase,
  contextDistributorMasterCollision,
  contextPossibleDuplicateOf,
  duplicateReviewDecision,
  hasUnresolvedDuplicateReview,
} from './dsiStewardCandidateFilterLogic';
import {
  optimisticallyApplyStewardAction,
  type DsiStewardRowAction,
} from './dsiStewardCacheUpdates';
import { DsiPendingButton } from './DsiPendingButton';
import {
  DsiEligibleProductPicker,
  type DsiEligibleProductSnapshot,
} from './DsiEligibleProductPicker';
import { toQueryError } from '@/lib/queryError';

export type DsiCandidateRow = {
  id: number;
  import_job_id: number;
  source_definition_id: number | null;
  entity_type: string;
  normalized_key: string;
  dealer_group_token: string | null;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
};

/** Same precedence as API ``raw_product_token_for_dsi_candidate`` — for steward UI defaults. */
export function dsiRawProductTokenForCandidate(
  candidate: Pick<DsiCandidateRow, 'sample_raw_values' | 'normalized_key'>
): string {
  const samples = candidate.sample_raw_values ?? [];
  for (const s of samples) {
    if (typeof s === 'string' && s.trim()) return s.trim().slice(0, 256);
  }
  const nk = (candidate.normalized_key || '').trim();
  if (nk && nk !== '__blank__') return nk.slice(0, 256);
  return '';
}

type RegionOpt = { id: number; code: string; name: string };
type ChannelOpt = { id: number; code: string; name: string };
type CustomerHit = { id: number; customer_code: string; customer_name: string };
type DistributorHit = { id: number; distributor_code: string; distributor_name: string };
type ProductHit = { id: number; sku: string; name: string; sales_model_name: string | null; is_active: boolean };

function strategicHint(ctx: Record<string, unknown> | null | undefined): boolean {
  return Boolean(ctx && ctx.strategic_channel_hint === true);
}

function blankishCustomerKey(norm: string): boolean {
  const t = (norm || '').trim().toLowerCase();
  return t === '' || t === '__blank__' || t === 'none' || t === 'n/a' || t === 'na' || t === 'unknown';
}

/**
 * Shared DSI mapping-queue steward workspace (single selected candidate).
 * Shipment evidence steward remains in `ShipmentEntityStewardPanel` under admin/shipment-evidence.
 */
type StewardMutationContext = { previous?: DsiCandidateRow[] };

function buildStewardMutationLifecycle(
  action: DsiStewardRowAction,
  candidateId: number | undefined,
  importJobId: number,
  qc: ReturnType<typeof useQueryClient>,
  onRowActionStart?: (candidateId: number) => void,
  onRowActionEnd?: () => void
) {
  const cacheKey = DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId);
  return {
    onMutate: async () => {
      if (candidateId == null) return undefined;
      onRowActionStart?.(candidateId);
      const previous = optimisticallyApplyStewardAction(qc, importJobId, candidateId, action);
      return { previous } satisfies StewardMutationContext;
    },
    onError: (_err: unknown, _vars: unknown, ctx: StewardMutationContext | undefined) => {
      if (ctx?.previous) qc.setQueryData(cacheKey, ctx.previous);
      onRowActionEnd?.();
    },
    onSettled: () => {
      onRowActionEnd?.();
    },
  };
}

const DSI_STEWARD_TERMINAL_STATUSES = new Set(['resolved', 'ignored', 'waived_open_channel']);

export function DsiMappingStewardPanel({
  importJobId,
  candidate,
  planRow,
  onRowActionStart,
  onRowActionEnd,
  onDone,
  onPlanRefresh,
  lookupPeerCandidate,
  onOpenPeerByNormalizedKey,
  customerNormalizedKeysOnPage,
  duplicateClusterMembers,
}: {
  importJobId: number;
  candidate: DsiCandidateRow | null;
  planRow?: Record<string, unknown> | null;
  onRowActionStart?: (candidateId: number) => void;
  onRowActionEnd?: () => void;
  onDone: () => void;
  /** Local resolution-plan refresh only — never full DSI revalidate. */
  onPlanRefresh?: () => void | Promise<void>;
  /** Resolve peer row on current candidates page for inline compare (no scroll jump). */
  lookupPeerCandidate?: (normalizedKey: string) => DsiCandidateRow | null;
  /** Optional: open peer in full steward drawer (replaces selection). */
  onOpenPeerByNormalizedKey?: (normalizedKey: string) => void;
  /** Customer token keys on the current candidates page (suffix-family display). */
  customerNormalizedKeysOnPage?: readonly string[];
  /** Connected duplicate cluster for the selected row (display only; from page candidates). */
  duplicateClusterMembers?: readonly string[];
}) {
  const qc = useQueryClient();
  const [expandedDuplicatePeerKey, setExpandedDuplicatePeerKey] = useState<string | null>(null);
  const [mapCustOpen, setMapCustOpen] = useState(false);
  const [createCustOpen, setCreateCustOpen] = useState(false);
  const [mapDistOpen, setMapDistOpen] = useState(false);
  const [createDistOpen, setCreateDistOpen] = useState(false);
  const [mapProdOpen, setMapProdOpen] = useState(false);
  const [ocOpen, setOcOpen] = useState(false);

  const [custQ, setCustQ] = useState('');
  const [distQ, setDistQ] = useState('');
  const [prodQ, setProdQ] = useState('');
  const [pickCustomerId, setPickCustomerId] = useState<number | ''>('');
  const [pickDistributorId, setPickDistributorId] = useState<number | ''>('');
  const [pickProductId, setPickProductId] = useState<number | ''>('');

  const [displayName, setDisplayName] = useState('');
  const [regionId, setRegionId] = useState<number | ''>('');
  const [channelId, setChannelId] = useState<number | ''>('');
  const [distDisplayName, setDistDisplayName] = useState('');
  const [distConfirmSuspicious, setDistConfirmSuspicious] = useState(false);
  const [ocNamedConfirm, setOcNamedConfirm] = useState(false);
  const [ocStrategicConfirm, setOcStrategicConfirm] = useState(false);
  const [confirmIneligibleProduct, setConfirmIneligibleProduct] = useState(false);
  const [productAuditNote, setProductAuditNote] = useState('');
  const [productRawOverride, setProductRawOverride] = useState('');
  const [lastSuccessLabel, setLastSuccessLabel] = useState<string | null>(null);
  const [dupSameOpen, setDupSameOpen] = useState(false);
  const [dupClusterOpen, setDupClusterOpen] = useState(false);
  const [dupPeerKey, setDupPeerKey] = useState('');
  const [dupDifferentPeerKey, setDupDifferentPeerKey] = useState('');

  useEffect(() => {
    setDupPeerKey('');
    setDupSameOpen(false);
    setDupClusterOpen(false);
    setExpandedDuplicatePeerKey(null);
    setDupDifferentPeerKey('');
  }, [candidate?.id]);

  const { data: regions = [] } = useQuery({
    queryKey: DSI_STEWARD_CONFIG.catalogRegionsQueryKey(),
    queryFn: ({ signal }) => apiGet<RegionOpt[]>('/api/v1/catalog/regions', { signal }),
  });
  const { data: channels = [] } = useQuery({
    queryKey: DSI_STEWARD_CONFIG.catalogChannelsQueryKey(),
    queryFn: ({ signal }) => apiGet<ChannelOpt[]>('/api/v1/catalog/channels', { signal }),
  });

  const { data: custHits = [] } = useQuery({
    queryKey: ['customers-search', custQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(`/api/v1/customers?q=${encodeURIComponent(custQ)}&page_size=20`, { signal }),
    enabled: custQ.trim().length >= 2,
    select: (r) => r.items ?? [],
  });

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorHit[] }>(
        `/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=20`,
        { signal }
      ),
    enabled: distQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const { data: prodHits = [] } = useQuery({
    queryKey: ['products-search-dsi-steward', prodQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: ProductHit[] }>(`/api/v1/products?q=${encodeURIComponent(prodQ)}&page_size=20`, { signal }),
    enabled: prodQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const invalidate = useCallback(() => {
    invalidateDsiImportJobStewardQueries(qc, importJobId);
    onDone();
  }, [qc, importJobId, onDone]);

  const afterDuplicateAction = useCallback(async () => {
    invalidateDsiImportJobStewardQueries(qc, importJobId);
    onDone();
    if (onPlanRefresh) await onPlanRefresh();
  }, [qc, importJobId, onDone, onPlanRefresh]);

  const candidateId = candidate?.id;
  const stewardLife = (action: DsiStewardRowAction) =>
    buildStewardMutationLifecycle(action, candidateId, importJobId, qc, onRowActionStart, onRowActionEnd);

  const duplicateRowLifecycle = {
    onMutate: async () => {
      if (candidateId != null) onRowActionStart?.(candidateId);
      return undefined;
    },
    onSettled: () => {
      onRowActionEnd?.();
    },
  };

  const duplicateDifferentEntity = useMutation({
    mutationFn: (body: { peer_normalized_key: string; audit_note?: string }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/duplicate-review/different-entity`,
        body
      ),
    ...duplicateRowLifecycle,
    onSuccess: async () => {
      setLastSuccessLabel('Confirmed different entity — duplicate review recorded.');
      await afterDuplicateAction();
    },
  });

  const duplicateSameEntity = useMutation({
    mutationFn: (body: {
      peer_normalized_key: string;
      customer_id?: number;
      display_name?: string;
      plan_suggested_target_id?: number;
      audit_note?: string;
    }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/duplicate-review/same-entity`,
        body
      ),
    ...duplicateRowLifecycle,
    onSuccess: async () => {
      setDupSameOpen(false);
      setLastSuccessLabel('Same entity — both tokens mapped to the selected customer.');
      await afterDuplicateAction();
    },
  });

  const duplicateClusterSameEntity = useMutation({
    mutationFn: (body: {
      normalized_keys: string[];
      customer_id?: number;
      display_name?: string;
      plan_suggested_target_id?: number;
      audit_note?: string;
    }) =>
      apiPost<{ ok: boolean; mapped_count?: number }>(
        `/api/v1/mappings/import-jobs/${importJobId}/duplicate-review/cluster-same-entity`,
        body
      ),
    ...duplicateRowLifecycle,
    onSuccess: async (data) => {
      setDupClusterOpen(false);
      const n = data?.mapped_count ?? 0;
      setLastSuccessLabel(`Cluster mapped — ${n} token(s) linked to one customer.`);
      await afterDuplicateAction();
    },
  });

  const mapCustomer = useMutation({
    mutationFn: (body: { customer_id: number }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/map-customer`, body),
    ...stewardLife('map_customer'),
    onSuccess: () => {
      setMapCustOpen(false);
      setLastSuccessLabel('Customer mapped — row updated.');
      invalidate();
    },
  });

  const createProvCustomer = useMutation({
    mutationFn: (body: {
      display_name: string;
      region_id: number;
      channel_id: number;
      preferred_distributor_id?: number | null;
    }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/create-provisional-customer`,
        body
      ),
    ...stewardLife('create_provisional_customer'),
    onSuccess: () => {
      setCreateCustOpen(false);
      setLastSuccessLabel('Provisional customer created — row updated.');
      invalidate();
    },
  });

  const markOpenChannel = useMutation({
    mutationFn: (body: { confirm_for_named_dealer: boolean; confirm_for_strategic_channel_hint: boolean }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/mark-open-channel`, body),
    ...stewardLife('mark_open_channel'),
    onSuccess: () => {
      setOcOpen(false);
      setLastSuccessLabel('Marked Open Channel — row updated.');
      invalidate();
    },
  });

  const ignoreCand = useMutation({
    mutationFn: (body: { notes?: string | null }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/ignore`, body),
    ...stewardLife('ignore'),
    onSuccess: () => {
      setLastSuccessLabel('Candidate ignored — row updated.');
      invalidate();
    },
  });

  const mapDistributor = useMutation({
    mutationFn: (body: { distributor_id: number }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/map-distributor`, body),
    ...stewardLife('map_distributor'),
    onSuccess: () => {
      setMapDistOpen(false);
      setLastSuccessLabel('Distributor mapped — row updated.');
      invalidate();
    },
  });

  const createProvDistributor = useMutation({
    mutationFn: (body: { display_name: string; confirm_for_suspicious_token: boolean }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/create-provisional-distributor`,
        body
      ),
    ...stewardLife('create_provisional_distributor'),
    onSuccess: () => {
      setCreateDistOpen(false);
      setLastSuccessLabel('Provisional distributor created — row updated.');
      invalidate();
    },
  });

  const resolveProduct = useMutation({
    mutationFn: (body: {
      product_id: number;
      raw_token?: string | null;
      confirm_ineligible_product: boolean;
      audit_note?: string | null;
    }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/resolve-product`, body),
    ...stewardLife('resolve_product'),
    onSuccess: () => {
      setMapProdOpen(false);
      setLastSuccessLabel('Product resolved — row updated.');
      invalidate();
    },
  });

  const revalidate = useMutation({
    mutationFn: async () => {
      const res = await apiPost<{ ok: boolean; async?: boolean; task_id?: string | null }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`
      );
      if (res.async) {
        notifyDsiAsyncPipelineStarted(qc, importJobId, { taskId: res.task_id });
      }
      return res;
    },
    onSuccess: (res) => {
      if (!res.async) invalidate();
      else void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
  });

  const actionBusy =
    mapCustomer.isPending ||
    createProvCustomer.isPending ||
    markOpenChannel.isPending ||
    ignoreCand.isPending ||
    mapDistributor.isPending ||
    createProvDistributor.isPending ||
    resolveProduct.isPending;

  /** Customer account (Dealer Name Group) vs source customer evidence — match DSI aggregation / mapping queue. */
  const stewardLabels = useMemo(() => {
    if (!candidate) {
      return { customerAccount: '', sourceCustomer: '', distributorOrProductLabel: '' };
    }
    const sampleFirst =
      candidate.sample_raw_values?.find((x) => x && String(x).trim()) || candidate.normalized_key || '';
    if (candidate.entity_type !== 'customer_dealer_token') {
      return { customerAccount: '', sourceCustomer: '', distributorOrProductLabel: String(sampleFirst) };
    }
    const c = (candidate.context ?? null) as Record<string, unknown> | null;
    const raw =
      typeof c?.dealer_group_account_raw === 'string' ? c.dealer_group_account_raw.trim() : '';
    const customerAccount = (raw || candidate.dealer_group_token || candidate.normalized_key || '').toString();
    const samples = c?.source_customer_name_raw_samples;
    let sourceCustomer = '';
    if (Array.isArray(samples)) {
      const parts = samples
        .filter((x) => typeof x === 'string' && x.trim())
        .map((x) => String(x).trim());
      if (parts.length) sourceCustomer = parts.join('; ');
    }
    return { customerAccount, sourceCustomer, distributorOrProductLabel: String(sampleFirst) };
  }, [candidate]);

  if (!candidate) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dsi-steward-no-selection">
        Select a candidate row in the grid to run steward actions (map, provisional create, Open Channel, ignore).
      </Typography>
    );
  }

  const ctx = (candidate.context ?? null) as Record<string, unknown> | null;
  const strat = strategicHint(ctx);
  const distCollision = contextDistributorMasterCollision(ctx);
  const dupHints = contextPossibleDuplicateOf(ctx);
  const histRes =
    planRow && typeof planRow.historical_resolution === 'object' && planRow.historical_resolution !== null
      ? (planRow.historical_resolution as Record<string, unknown>)
      : null;
  const dupDecision = duplicateReviewDecision(ctx);
  const dupUnresolved =
    candidate.entity_type === 'customer_dealer_token' && hasUnresolvedDuplicateReview(ctx);
  const isTerminal = DSI_STEWARD_TERMINAL_STATUSES.has((candidate.status || '').trim());
  const rowActionsBlocked = isDsiStewardRowActionBlocked(candidate.status);
  const stewardActionsDisabled = isTerminal || rowActionsBlocked || actionBusy;
  const planDuplicateBlocked = planRow?.duplicate_review_required === true;
  const dupPeerHintsExcludingSelf = useMemo(() => {
    const own = (candidate.normalized_key || '').trim();
    return dupHints.filter((h) => h.normalized_key.trim() !== own);
  }, [dupHints, candidate.normalized_key]);
  const dupPeerKeyDefault = dupPeerHintsExcludingSelf[0]?.normalized_key ?? '';
  const dupPeerForSameEntity = useMemo(
    () => (dupPeerKeyDefault && lookupPeerCandidate ? lookupPeerCandidate(dupPeerKeyDefault) : null),
    [dupPeerKeyDefault, lookupPeerCandidate]
  );
  const dupSameEntityCaseLive = useMemo(
    () =>
      classifyDuplicateSameEntityCase(
        candidate.suggested_entity_id,
        dupPeerForSameEntity?.suggested_entity_id,
        planRow?.suggested_target_id
      ),
    [candidate.suggested_entity_id, dupPeerForSameEntity?.suggested_entity_id, planRow?.suggested_target_id]
  );
  const dupSameEntityConflict = dupUnresolved && !isTerminal && dupSameEntityCaseLive === 'conflict';
  const suffixTokenFamily = useMemo(
    () =>
      candidate.entity_type === 'customer_dealer_token' && customerNormalizedKeysOnPage?.length
        ? detectSuffixTokenFamily(candidate.normalized_key, customerNormalizedKeysOnPage)
        : null,
    [candidate.entity_type, candidate.normalized_key, customerNormalizedKeysOnPage]
  );
  const clusterPeersExcludingSelf = useMemo(() => {
    const own = (candidate.normalized_key || '').trim();
    const members = duplicateClusterMembers ?? [];
    return members.filter((k) => k.trim() !== own);
  }, [duplicateClusterMembers, candidate.normalized_key]);

  useEffect(() => {
    const first = dupPeerHintsExcludingSelf[0]?.normalized_key ?? '';
    setDupDifferentPeerKey(first);
  }, [candidate.id, dupPeerHintsExcludingSelf]);

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="dsi-steward-panel">
      <Alert severity="info">
        Provisional records are created as <strong>unverified</strong> and editable. They give facts a stable system ID
        without implying the profile is complete. Open Channel / blank inventory evidence must not create fake
        customers—use <strong>Mark Open Channel</strong> only for blank or explicitly confirmed cases.
      </Alert>
      {strat ? (
        <Alert severity="warning" data-testid="dsi-strategic-hint-alert">
          Channel evidence resembles a strategic marketplace or major retail chain. Do not assume Open Channel—map or
          create a customer, or confirm explicitly if Open Channel is correct.
        </Alert>
      ) : null}
      {distCollision ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-inter-disti-hint">
          <Typography variant="body2">
            This token matches distributor master <strong>{distCollision.distributor_name}</strong>. On this file it is
            a <strong>sell-out counterparty</strong> (often inter-distributor transfer). You may still map as{' '}
            <strong>customer</strong> for analysis on the selling distributor&apos;s file. It does{' '}
            <strong>not</strong> update the buyer&apos;s inventory SOH — that comes from their own DSI inventory import.
          </Typography>
        </Alert>
      ) : null}
      {suffixTokenFamily && suffixTokenFamily.length >= 3 ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-suffix-token-family">
          <Typography variant="body2">
            <strong>Suffix token family</strong> (informational — not auto-duplicates):{' '}
            {suffixTokenFamily.map((k) => (
              <code key={k} style={{ marginRight: 6 }}>
                {k}
              </code>
            ))}
            . Review each token separately; only scored pairs appear under possible duplicates.
          </Typography>
        </Alert>
      ) : null}
      {clusterPeersExcludingSelf.length > 0 ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-duplicate-cluster">
          <Typography variant="body2" component="div">
            <strong>Duplicate cluster on this page</strong> ({clusterPeersExcludingSelf.length + 1} tokens linked by
            hints):{' '}
            <code>{candidate.normalized_key}</code>
            {clusterPeersExcludingSelf.map((k) => (
              <span key={k}>
                {', '}
                <code>{k}</code>
              </span>
            ))}
            . Confirm pairwise Same/Different, or map the whole cluster to one customer when you are sure they are the
            same legal entity.
          </Typography>
          {dupUnresolved && !isTerminal ? (
            <Box sx={{ mt: 1 }}>
              <DsiPendingButton
                size="small"
                variant="outlined"
                data-testid="dsi-duplicate-cluster-map"
                onClick={() => setDupClusterOpen(true)}
              >
                Map cluster to one customer…
              </DsiPendingButton>
            </Box>
          ) : null}
        </Alert>
      ) : null}
      {dupHints.length > 0 ? (
        <Alert
          severity={dupUnresolved ? 'warning' : 'info'}
          variant="outlined"
          data-testid="dsi-possible-duplicates"
        >
          <Typography variant="body2" component="div">
            <strong>Possible duplicates</strong> (same import job, name similarity after normalisation):
            <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
              {dupHints.map((d) => (
                <li key={d.normalized_key}>
                  <code>{d.normalized_key}</code>
                  {d.similarity_score != null
                    ? ` — ${Math.round(d.similarity_score * 100)}% similar`
                    : ''}
                  {lookupPeerCandidate || onOpenPeerByNormalizedKey ? (
                    <>
                      {' '}
                      <Typography
                        component="button"
                        type="button"
                        variant="caption"
                        sx={{
                          border: 0,
                          bgcolor: 'transparent',
                          color: 'primary.main',
                          cursor: 'pointer',
                          textDecoration: 'underline',
                          p: 0,
                        }}
                        onClick={() =>
                          setExpandedDuplicatePeerKey((k) =>
                            k === d.normalized_key ? null : d.normalized_key
                          )
                        }
                        data-testid="dsi-duplicate-peer-compare-toggle"
                      >
                        {expandedDuplicatePeerKey === d.normalized_key ? 'Hide compare' : 'Compare'}
                      </Typography>
                    </>
                  ) : null}
                  {expandedDuplicatePeerKey === d.normalized_key ? (
                    <DsiDuplicatePeerCompare
                      normalizedKey={d.normalized_key}
                      lookupPeerCandidate={lookupPeerCandidate}
                      onOpenFullSteward={onOpenPeerByNormalizedKey}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
            {dupDecision ? (
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                Steward decision: <strong>{dupDecision.replace(/_/g, ' ')}</strong>
              </Typography>
            ) : null}
            {dupSameEntityConflict ? (
              <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 1 }}>
                These tokens have conflicting customer suggestions. Resolve each separately.
              </Typography>
            ) : null}
            {dupUnresolved && !isTerminal ? (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
                <DsiPendingButton
                  size="small"
                  variant="contained"
                  pending={duplicateSameEntity.isPending}
                  pendingLabel="Mapping…"
                  disabled={
                    actionBusy ||
                    duplicateDifferentEntity.isPending ||
                    dupSameEntityConflict ||
                    dupPeerHintsExcludingSelf.length === 0
                  }
                  onClick={() => {
                    const peerKey = dupPeerHintsExcludingSelf[0]?.normalized_key ?? '';
                    const peerRow = lookupPeerCandidate?.(peerKey) ?? null;
                    const caseKind = classifyDuplicateSameEntityCase(
                      candidate.suggested_entity_id,
                      peerRow?.suggested_entity_id,
                      planRow?.suggested_target_id
                    );
                    if (caseKind === 'conflict') return;
                    setDupPeerKey(peerKey);
                    setDupSameOpen(true);
                  }}
                  data-testid="dsi-duplicate-same-entity"
                >
                  Same entity (map both)
                </DsiPendingButton>
                <DsiPendingButton
                  size="small"
                  variant="outlined"
                  pending={duplicateDifferentEntity.isPending}
                  pendingLabel="Saving…"
                  disabled={
                    actionBusy || duplicateSameEntity.isPending || !dupDifferentPeerKey.trim()
                  }
                  onClick={() =>
                    void duplicateDifferentEntity.mutateAsync({
                      peer_normalized_key: dupDifferentPeerKey.trim(),
                    })
                  }
                  data-testid="dsi-duplicate-different-entity"
                >
                  Different entity
                </DsiPendingButton>
              </Stack>
            ) : null}
            {planDuplicateBlocked ? (
              <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 1 }}>
                Resolution plan is blocked until duplicate review is complete.
              </Typography>
            ) : null}
          </Typography>
        </Alert>
      ) : null}
      {histRes ? (
        <Alert severity="warning" variant="outlined" data-testid="dsi-historical-resolution">
          <Typography variant="body2">
            <strong>Previously resolved</strong> on import job {String(histRes.import_job_id ?? '—')} → customer{' '}
            {String(histRes.customer_id ?? '—')}
            {typeof histRes.confidence === 'number'
              ? ` (${Math.round(Number(histRes.confidence) * 100)}% confidence)`
              : ''}
            . Confirm mapping — not auto-applied.
          </Typography>
        </Alert>
      ) : null}
      <Typography variant="body2" component="div">
        <strong>Selected:</strong> {candidate.entity_type} · normalized: {candidate.normalized_key}
        {stewardLabels.customerAccount ? ` · customer account: ${stewardLabels.customerAccount}` : ''}
        {stewardLabels.sourceCustomer ? ` · source customer: ${stewardLabels.sourceCustomer}` : ''} · status{' '}
        {candidate.status}
        {actionBusy ? (
          <>
            {' '}
            <Chip size="small" color="info" label="Saving…" data-testid="dsi-steward-row-saving" />
          </>
        ) : null}
      </Typography>
      {rowActionsBlocked && !isTerminal ? (
        <Alert severity="info" data-testid="dsi-steward-row-actions-blocked">
          Duplicate review recorded for this row — mapping actions are disabled. Select another token or close the
          steward panel.
        </Alert>
      ) : null}
      {lastSuccessLabel && !actionBusy ? (
        <Alert severity="success" onClose={() => setLastSuccessLabel(null)} data-testid="dsi-steward-row-success">
          {lastSuccessLabel}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={createProvCustomer.isPending}
          pendingLabel="Creating…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setDisplayName(
              stewardLabels.customerAccount || candidate.normalized_key || stewardLabels.distributorOrProductLabel
            );
            if (regions[0]) setRegionId(regions[0].id);
            if (channels[0]) setChannelId(channels[0].id);
            setCreateCustOpen(true);
          }}
          data-testid="dsi-action-create-provisional-customer"
        >
          Create provisional customer
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={mapCustomer.isPending}
          pendingLabel="Mapping…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setCustQ('');
            setPickCustomerId('');
            setMapCustOpen(true);
          }}
          data-testid="dsi-action-map-customer"
        >
          Map to existing customer
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={markOpenChannel.isPending}
          pendingLabel="Saving…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setOcNamedConfirm(false);
            setOcStrategicConfirm(false);
            setOcOpen(true);
          }}
          data-testid="dsi-action-open-channel"
        >
          Mark Open Channel (alias)
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={mapDistributor.isPending}
          pendingLabel="Mapping…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'distributor_token'}
          onClick={() => {
            setDistQ('');
            setPickDistributorId('');
            setMapDistOpen(true);
          }}
          data-testid="dsi-action-map-distributor"
        >
          Map to existing distributor
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={createProvDistributor.isPending}
          pendingLabel="Creating…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'distributor_token'}
          onClick={() => {
            setDistDisplayName(stewardLabels.distributorOrProductLabel);
            setDistConfirmSuspicious(false);
            setCreateDistOpen(true);
          }}
          data-testid="dsi-action-create-provisional-distributor"
        >
          Create provisional distributor
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          size="small"
          pending={resolveProduct.isPending}
          pendingLabel="Resolving…"
          disabled={stewardActionsDisabled || candidate.entity_type !== 'product_identifier'}
          onClick={() => {
            setProdQ(dsiRawProductTokenForCandidate(candidate));
            setPickProductId('');
            setConfirmIneligibleProduct(false);
            setProductAuditNote('');
            setProductRawOverride('');
            setMapProdOpen(true);
          }}
          data-testid="dsi-action-resolve-product"
        >
          Map to Product Master (alias)
        </DsiPendingButton>
        <DsiPendingButton
          variant="outlined"
          color="warning"
          size="small"
          pending={ignoreCand.isPending}
          pendingLabel="Ignoring…"
          disabled={stewardActionsDisabled}
          onClick={() => void ignoreCand.mutateAsync({ notes: null }).catch(() => {})}
          data-testid="dsi-action-ignore"
        >
          Ignore candidate
        </DsiPendingButton>
      </Stack>
      {(mapCustomer.isError ||
        createProvCustomer.isError ||
        markOpenChannel.isError ||
        mapDistributor.isError ||
        createProvDistributor.isError ||
        resolveProduct.isError ||
        ignoreCand.isError ||
        duplicateSameEntity.isError) && (
        <Alert severity="error">
          {toQueryError(
            mapCustomer.error ||
              createProvCustomer.error ||
              markOpenChannel.error ||
              mapDistributor.error ||
              createProvDistributor.error ||
              resolveProduct.error ||
              ignoreCand.error ||
              duplicateSameEntity.error
          )?.message ?? 'Action failed'}
        </Alert>
      )}

      <Dialog open={mapCustOpen} onClose={() => setMapCustOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Map to existing customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Search customers"
              value={custQ}
              onChange={(e) => setCustQ(e.target.value)}
              helperText="Type at least 2 characters"
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="pick-cust">Customer</InputLabel>
              <Select
                labelId="pick-cust"
                label="Customer"
                value={pickCustomerId === '' ? '' : String(pickCustomerId)}
                onChange={(e) => setPickCustomerId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {custHits.map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.customer_code} — {c.customer_name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setMapCustOpen(false)} disabled={mapCustomer.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={mapCustomer.isPending}
            pendingLabel="Saving…"
            disabled={pickCustomerId === ''}
            onClick={() => {
              if (pickCustomerId === '') return;
              void mapCustomer.mutateAsync({ customer_id: Number(pickCustomerId) }).catch(() => {});
            }}
          >
            Save alias
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      <DsiDuplicateSameEntityDialog
        open={dupSameOpen}
        onClose={() => setDupSameOpen(false)}
        pending={duplicateSameEntity.isPending}
        primaryCandidate={candidate}
        peerNormalizedKey={dupPeerKey}
        peerCandidate={lookupPeerCandidate?.(dupPeerKey) ?? null}
        planRow={planRow}
        onSubmit={(body) => {
          void duplicateSameEntity.mutateAsync(body).catch(() => {});
        }}
      />

      <DsiDuplicateClusterSameEntityDialog
        open={dupClusterOpen}
        onClose={() => setDupClusterOpen(false)}
        pending={duplicateClusterSameEntity.isPending}
        importJobId={importJobId}
        primaryCandidate={candidate}
        clusterNormalizedKeys={duplicateClusterMembers ?? [candidate.normalized_key]}
        planRow={planRow}
        onSubmit={(body) => {
          void duplicateClusterSameEntity.mutateAsync(body).catch(() => {});
        }}
      />

      <Dialog open={createCustOpen} onClose={() => setCreateCustOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create provisional customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel id="reg">Region</InputLabel>
              <Select
                labelId="reg"
                label="Region"
                value={regionId === '' ? '' : String(regionId)}
                onChange={(e) => setRegionId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {regions.map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>
                    {r.code} — {r.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="ch">Channel</InputLabel>
              <Select
                labelId="ch"
                label="Channel"
                value={channelId === '' ? '' : String(channelId)}
                onChange={(e) => setChannelId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {channels.map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.code} — {c.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setCreateCustOpen(false)} disabled={createProvCustomer.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={createProvCustomer.isPending}
            pendingLabel="Creating…"
            disabled={!displayName.trim() || regionId === '' || channelId === ''}
            onClick={() =>
              void createProvCustomer
                .mutateAsync({
                  display_name: displayName.trim(),
                  region_id: Number(regionId),
                  channel_id: Number(channelId),
                })
                .catch(() => {})
            }
          >
            Create &amp; alias
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      <Dialog open={ocOpen} onClose={() => setOcOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Mark Open Channel</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Saves an approved alias to the Open Channel customer for this token. Named dealers require explicit
              confirmation; strategic channel hints require a separate confirmation.
            </Typography>
            {!blankishCustomerKey(candidate.normalized_key) ? (
              <label>
                <input
                  type="checkbox"
                  checked={ocNamedConfirm}
                  onChange={(e) => setOcNamedConfirm(e.target.checked)}
                  data-testid="dsi-oc-named-confirm"
                />{' '}
                I confirm mapping this named dealer token to Open Channel
              </label>
            ) : null}
            {strat ? (
              <label>
                <input
                  type="checkbox"
                  checked={ocStrategicConfirm}
                  onChange={(e) => setOcStrategicConfirm(e.target.checked)}
                  data-testid="dsi-oc-strategic-confirm"
                />{' '}
                I confirm Open Channel despite strategic / marketplace-style channel evidence
              </label>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setOcOpen(false)} disabled={markOpenChannel.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={markOpenChannel.isPending}
            pendingLabel="Saving…"
            disabled={
              (!blankishCustomerKey(candidate.normalized_key) && !ocNamedConfirm) ||
              (strat && !ocStrategicConfirm)
            }
            onClick={() =>
              void markOpenChannel
                .mutateAsync({
                  confirm_for_named_dealer: !blankishCustomerKey(candidate.normalized_key) ? ocNamedConfirm : false,
                  confirm_for_strategic_channel_hint: strat ? ocStrategicConfirm : false,
                })
                .catch(() => {})
            }
          >
            Save Open Channel alias
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      <Dialog open={mapDistOpen} onClose={() => setMapDistOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Map to existing distributor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Search distributors" value={distQ} onChange={(e) => setDistQ(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel id="pick-dist">Distributor</InputLabel>
              <Select
                labelId="pick-dist"
                label="Distributor"
                value={pickDistributorId === '' ? '' : String(pickDistributorId)}
                onChange={(e) => setPickDistributorId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {distHits.map((d) => (
                  <MenuItem key={d.id} value={String(d.id)}>
                    {d.distributor_code} — {d.distributor_name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setMapDistOpen(false)} disabled={mapDistributor.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={mapDistributor.isPending}
            pendingLabel="Saving…"
            disabled={pickDistributorId === ''}
            onClick={() => {
              if (pickDistributorId === '') return;
              void mapDistributor.mutateAsync({ distributor_id: Number(pickDistributorId) }).catch(() => {});
            }}
          >
            Save alias
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      <Dialog open={createDistOpen} onClose={() => setCreateDistOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create provisional distributor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Display name"
              value={distDisplayName}
              onChange={(e) => setDistDisplayName(e.target.value)}
              fullWidth
            />
            <label>
              <input
                type="checkbox"
                checked={distConfirmSuspicious}
                onChange={(e) => setDistConfirmSuspicious(e.target.checked)}
                data-testid="dsi-dist-suspicious-confirm"
              />{' '}
              Confirm create despite placeholder-like distributor token
            </label>
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setCreateDistOpen(false)} disabled={createProvDistributor.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={createProvDistributor.isPending}
            pendingLabel="Creating…"
            disabled={!distDisplayName.trim()}
            onClick={() =>
              void createProvDistributor
                .mutateAsync({
                  display_name: distDisplayName.trim(),
                  confirm_for_suspicious_token: distConfirmSuspicious,
                })
                .catch(() => {})
            }
          >
            Create &amp; alias
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      <Dialog open={mapProdOpen} onClose={() => setMapProdOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Map product token to Product Master</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Creates an approved <strong>ProductAlias</strong> for this import token, then mark this candidate resolved.
              Run <strong>Revalidate import job</strong> (here or on the mapping queue page) so staging picks up the new
              alias.
            </Typography>
            <Alert severity="info" data-testid="dsi-product-dialog-source-token">
              <Typography variant="body2" component="div">
                <strong>Source product token</strong> (used for the alias unless you override below):{' '}
                <code>{dsiRawProductTokenForCandidate(candidate) || '—'}</code>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                Normalized grouping key: <code>{candidate.normalized_key || '—'}</code>
                {typeof ctx?.product_match_summary === 'string' && ctx.product_match_summary.trim() ? (
                  <>
                    <br />
                    Match context: {String(ctx.product_match_summary)}
                  </>
                ) : null}
              </Typography>
            </Alert>
            <TextField
              label="Search products (SKU / model)"
              value={prodQ}
              onChange={(e) => setProdQ(e.target.value)}
              helperText="Pre-filled from the file token above; edit to narrow Product Master search."
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="pick-prod">Product</InputLabel>
              <Select
                labelId="pick-prod"
                label="Product"
                value={pickProductId === '' ? '' : String(pickProductId)}
                onChange={(e) => setPickProductId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {prodHits.map((p) => (
                  <MenuItem key={p.id} value={String(p.id)}>
                    {p.sku} — {p.name}
                    {p.sales_model_name ? ` (${p.sales_model_name})` : ''}
                    {!p.is_active ? ' [inactive]' : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Raw token override (optional)"
              value={productRawOverride}
              onChange={(e) => setProductRawOverride(e.target.value)}
              helperText="Leave blank to use candidate samples / normalized token"
              fullWidth
            />
            <label>
              <input
                type="checkbox"
                checked={confirmIneligibleProduct}
                onChange={(e) => setConfirmIneligibleProduct(e.target.checked)}
                data-testid="dsi-product-ineligible-confirm"
              />{' '}
              Confirm mapping to an inactive / ineligible Product Master row (requires audit note)
            </label>
            <TextField
              label="Audit note (required if confirming inactive/ineligible)"
              value={productAuditNote}
              onChange={(e) => setProductAuditNote(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <DsiPendingButton onClick={() => setMapProdOpen(false)} disabled={resolveProduct.isPending}>
            Cancel
          </DsiPendingButton>
          <DsiPendingButton
            variant="contained"
            pending={resolveProduct.isPending}
            pendingLabel="Saving…"
            disabled={pickProductId === ''}
            onClick={() => {
              if (pickProductId === '') return;
              const rawTok = productRawOverride.trim() || undefined;
              void resolveProduct
                .mutateAsync({
                  product_id: Number(pickProductId),
                  raw_token: rawTok,
                  confirm_ineligible_product: confirmIneligibleProduct,
                  audit_note: productAuditNote.trim() || undefined,
                })
                .catch(() => {});
            }}
            data-testid="dsi-product-resolve-save"
          >
            Save ProductAlias &amp; resolve
          </DsiPendingButton>
        </DialogActions>
      </Dialog>

      {candidate.entity_type === 'product_identifier' ? (
        <Stack spacing={1}>
          <Alert severity="warning" data-testid="dsi-product-guidance">
            Product identifiers are governed through Product Master / ProductAlias. Map via Product Master workflows; this
            screen does not create products or provisional SKUs.
          </Alert>
          {typeof ctx?.product_match_summary === 'string' && ctx.product_match_summary.trim() ? (
            <Alert severity="info" data-testid="dsi-product-match-summary">
              <Typography variant="body2">{String(ctx.product_match_summary)}</Typography>
              {ctx.product_match_status === 'ambiguous_eligible' && Array.isArray(ctx.product_ambiguous_eligible?.eligible_products) ? (
                <Box sx={{ mt: 1 }}>
                  <DsiEligibleProductPicker
                    tier={String((ctx.product_ambiguous_eligible as Record<string, unknown>).tier ?? '')}
                    products={
                      Array.isArray((ctx.product_ambiguous_eligible as Record<string, unknown>).eligible_products)
                        ? ((ctx.product_ambiguous_eligible as Record<string, unknown>)
                            .eligible_products as DsiEligibleProductSnapshot[])
                        : []
                    }
                    selectedProductId={pickProductId}
                    onSelectProductId={(id) => setPickProductId(id)}
                    disabled={resolveProduct.isPending}
                  />
                </Box>
              ) : null}
              {ctx.product_match_status === 'inactive_only' && Array.isArray(ctx.product_inactive_matches) ? (
                <Typography variant="caption" component="div" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(ctx.product_inactive_matches, null, 2)}
                </Typography>
              ) : null}
            </Alert>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}

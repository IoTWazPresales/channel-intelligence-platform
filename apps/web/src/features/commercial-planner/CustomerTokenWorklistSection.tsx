/**
 * Customer-token stamp worklist — first live `opts.target` consumer (Unit 6b / BACKLOG-112/123).
 * STAMP requiresTarget + previewFirst; target MUST flow applyItems(..., { target }) → API.
 */
'use client';

import { useMemo, useState, type InputHTMLAttributes } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';
import {
  ResolutionWorklist,
  type ResolutionApplyResult,
  type ResolutionBucket,
  type ResolutionSyncApplyAdapter,
  type ResolutionTargetSelection,
} from '@/features/steward-worklist';

export type CustomerTokenWorkItem = {
  item_key: string;
  norm_token: string;
  sample_token: string;
  line_count: number;
  line_ids?: number[];
  case_id?: number;
  bucket: 'clean' | 'specificity' | 'genuine_conflict' | 'empty_token' | 'distributor_token' | string;
  alias_candidates: ResolutionTargetSelection[];
  preferred_target_id: number | null;
  stamp_enabled: boolean;
  free_target_allowed?: boolean;
  tokenless?: boolean;
  conflict: boolean;
  competing_customer_ids: number[];
  dispositions: string[];
  sole_po_customer_count?: number;
  distributor_token_match?: {
    distributor_id: number;
    matched_via: string;
    matched_key: string;
  } | null;
  would_set_attribution_status?: string | null;
  ship_corroboration_offer?: {
    distributor_id: number;
    reason: string;
    exact_qty_ship_count?: number;
    eligible_dist_count?: number;
  } | null;
};

type WorklistResponse = {
  items: CustomerTokenWorkItem[];
  total: number;
  bucket_counts: Record<string, number>;
  open_channel_customer_id?: number | null;
};

type PreviewResponse = {
  line_count: number;
  target_customer_label: string;
  current_resolution_breakdown?: Record<string, number>;
  would_create_alias?: boolean;
  mints_alias?: boolean;
  writes_customer_token?: boolean;
  sample_lines?: Array<{ line_id: number; case_id: number; customer_id: number | null }>;
  sample_line_ids?: number[];
  case_ids?: number[];
  rejected_count?: number;
};

type ApplyResponse = {
  alias_id: number;
  stamped_count: number;
  norm_token: string;
  target_customer_id: number;
};

type MintedAliasesResponse = {
  aliases: Array<{
    alias_id: number;
    norm_token: string;
    customer_id: number;
    status: string;
  }>;
};

type BucketId = 'all' | 'clean' | 'specificity' | 'genuine_conflict' | 'distributor_token' | 'empty_token';

function preferredTarget(item: CustomerTokenWorkItem): ResolutionTargetSelection | null {
  // BACKLOG-124: ship/PO hints only — never auto-select for empty_token
  if (item.tokenless || item.bucket === 'empty_token') return null;
  if (!item.alias_candidates.length) return null;
  const pref = item.preferred_target_id;
  if (pref != null) {
    const hit = item.alias_candidates.find((t) => t.targetKey === String(pref));
    if (hit) return hit;
  }
  // Specificity: never default to OPEN_CHANNEL (meta.is_open_channel)
  const named = item.alias_candidates.find((t) => !t.meta?.is_open_channel);
  if (item.bucket === 'specificity' && named) return named;
  return item.alias_candidates[0] ?? null;
}

export const CUSTOMER_TOKEN_SECTION_ID = 'customer-token-stamp-section';

export function CustomerTokenWorklistSection() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [bucket, setBucket] = useState<BucketId>('all');
  const [picked, setPicked] = useState<ResolutionTargetSelection | null>(null);
  const [stampItem, setStampItem] = useState<CustomerTokenWorkItem | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [reason, setReason] = useState('steward customer-token stamp');
  const [freeTargetId, setFreeTargetId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [conflictBanner, setConflictBanner] = useState<{
    norm_token: string;
    competing_customer_ids: number[];
    dispositions: string[];
  } | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [revokeAliasId, setRevokeAliasId] = useState<number | null>(null);
  const [revokeReason, setRevokeReason] = useState('steward revoke');

  const worklistQ = useQuery({
    queryKey: ['customer-token-worklist'],
    queryFn: ({ signal }) =>
      apiGet<WorklistResponse>('/api/v1/commercial-planner/lineup/customer-token/worklist?limit=200', {
        signal,
      }),
  });

  const mintedQ = useQuery({
    queryKey: ['customer-token-minted-aliases'],
    queryFn: ({ signal }) =>
      apiGet<MintedAliasesResponse>(
        '/api/v1/commercial-planner/lineup/customer-token/minted-aliases?limit=50',
        { signal },
      ),
  });

  const items = worklistQ.data?.items ?? [];
  const byKey = useMemo(() => {
    const m = new Map<string, CustomerTokenWorkItem>();
    for (const it of items) m.set(it.item_key, it);
    return m;
  }, [items]);

  const filtered = useMemo(() => {
    if (bucket === 'all') return items;
    return items.filter((i) => i.bucket === bucket);
  }, [items, bucket]);

  const buckets: ResolutionBucket<BucketId>[] = useMemo(() => {
    const c = worklistQ.data?.bucket_counts ?? {};
    return [
      { id: 'all', label: 'All', count: c.all ?? items.length },
      { id: 'clean', label: 'Clean', count: c.clean ?? 0 },
      { id: 'specificity', label: 'Specificity', count: c.specificity ?? 0 },
      { id: 'distributor_token', label: 'Distributor', count: c.distributor_token ?? 0 },
      { id: 'genuine_conflict', label: 'Conflict', count: c.genuine_conflict ?? 0 },
      { id: 'empty_token', label: 'Empty token', count: c.empty_token ?? 0 },
    ];
  }, [worklistQ.data?.bucket_counts, items.length]);

  const previewMut = useMutation({
    mutationFn: (vars: {
      mode: 'token' | 'tokenless';
      norm_token?: string;
      line_ids?: number[];
      target_customer_id: number;
    }) =>
      vars.mode === 'tokenless'
        ? apiPost<PreviewResponse>(
            '/api/v1/commercial-planner/lineup/customer-token/tokenless/preview',
            {
              line_ids: vars.line_ids ?? [],
              target_customer_id: vars.target_customer_id,
            },
          )
        : apiPost<PreviewResponse>('/api/v1/commercial-planner/lineup/customer-token/stamp/preview', {
            norm_token: vars.norm_token ?? '',
            target_customer_id: vars.target_customer_id,
          }),
  });

  const [stampPending, setStampPending] = useState(false);

  const revokeMut = useMutation({
    mutationFn: (vars: { alias_id: number; reason: string }) =>
      apiPost<{ revoked_alias_id: number; unwound_count: number }>(
        '/api/v1/commercial-planner/lineup/customer-token/alias/revoke',
        vars,
      ),
    onSuccess: (data) => {
      setSuccess(`Revoked alias ${data.revoked_alias_id}; unwound ${data.unwound_count} line(s)`);
      setRevokeAliasId(null);
      void qc.invalidateQueries({ queryKey: ['customer-token-worklist'] });
      void qc.invalidateQueries({ queryKey: ['customer-token-minted-aliases'] });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : 'Revoke failed');
    },
  });

  const acceptShipMut = useMutation({
    mutationFn: (vars: { norm_token: string; distributor_id: number; reason: string }) =>
      apiPost<{ stamped_count: number; distributor_id: number; status: string }>(
        '/api/v1/commercial-planner/lineup/distributor-attribution/accept-ship',
        vars,
      ),
    onSuccess: (data) => {
      setSuccess(
        `Accepted ship-corroborated distributor ${data.distributor_id} on ${data.stamped_count} line(s) (${data.status})`,
      );
      void qc.invalidateQueries({ queryKey: ['customer-token-worklist'] });
      void qc.invalidateQueries({ queryKey: ['customer-token-minted-aliases'] });
      void qc.invalidateQueries({ queryKey: ['distributor-attribution-review'] });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : 'Accept ship corroboration failed');
    },
  });

  /** FIRST LIVE opts.target — target_customer_id ONLY from opts.target.targetKey */
  const applyAdapter: ResolutionSyncApplyAdapter<CustomerTokenWorkItem> = {
    mode: 'sync',
    applyItems: async (batch, opts) => {
      const target = opts?.target;
      if (!target) {
        return {
          results: batch.map((i) => ({
            key: i.item_key,
            status: 'error' as const,
            message: 'target required via opts.target',
          })),
          applied: 0,
          alreadyDone: 0,
          skippedProtected: 0,
          errors: batch.length,
        };
      }
      const targetCustomerId = Number(target.targetKey);
      if (!Number.isFinite(targetCustomerId) || targetCustomerId < 1) {
        return {
          results: batch.map((i) => ({
            key: i.item_key,
            status: 'error' as const,
            message: 'invalid opts.target.targetKey',
          })),
          applied: 0,
          alreadyDone: 0,
          skippedProtected: 0,
          errors: batch.length,
        };
      }
      const results: ResolutionApplyResult['results'] = [];
      let applied = 0;
      let errors = 0;
      for (const item of batch) {
        try {
          if (item.tokenless || item.bucket === 'empty_token') {
            const lineIds = item.line_ids ?? [];
            if (!lineIds.length) {
              throw new Error('tokenless stamp requires line_ids');
            }
            await apiPost<{ stamped_count: number }>(
              '/api/v1/commercial-planner/lineup/customer-token/tokenless/apply',
              {
                line_ids: lineIds,
                target_customer_id: targetCustomerId,
                reason,
              },
            );
          } else {
            await apiPost<ApplyResponse>('/api/v1/commercial-planner/lineup/customer-token/stamp/apply', {
              norm_token: item.norm_token,
              target_customer_id: targetCustomerId,
              reason,
            });
          }
          results.push({ key: item.item_key, status: 'applied' });
          applied += 1;
        } catch (err: unknown) {
          const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
            ?.detail;
          if (detail && typeof detail === 'object' && (detail as { conflict?: boolean }).conflict) {
            const d = detail as {
              norm_token: string;
              competing_customer_ids: number[];
              dispositions: string[];
            };
            setConflictBanner({
              norm_token: d.norm_token,
              competing_customer_ids: d.competing_customer_ids ?? [],
              dispositions: d.dispositions ?? ['scoped', 'merge', 'data_error'],
            });
          }
          results.push({
            key: item.item_key,
            status: 'error',
            message: err instanceof Error ? err.message : 'stamp error',
          });
          errors += 1;
        }
      }
      void qc.invalidateQueries({ queryKey: ['customer-token-worklist'] });
      void qc.invalidateQueries({ queryKey: ['customer-token-minted-aliases'] });
      return { results, applied, alreadyDone: 0, skippedProtected: 0, errors };
    },
  };

  const openStamp = async (item: CustomerTokenWorkItem, target: ResolutionTargetSelection) => {
    setError(null);
    setConflictBanner(null);
    setStampItem(item);
    setPicked(target);
    const tokenless = Boolean(item.tokenless || item.bucket === 'empty_token');
    const prev = await previewMut.mutateAsync(
      tokenless
        ? {
            mode: 'tokenless',
            line_ids: item.line_ids ?? [],
            target_customer_id: Number(target.targetKey),
          }
        : {
            mode: 'token',
            norm_token: item.norm_token,
            target_customer_id: Number(target.targetKey),
          },
    );
    setPreview(prev);
  };

  const confirmStamp = async () => {
    if (!stampItem || !picked) return;
    setStampPending(true);
    try {
      // Prove opts.target path: apply via adapter, not a side-channel body builder
      const result = await applyAdapter.applyItems([stampItem], { target: picked });
      if (result.applied > 0) {
        setSuccess(`Stamped via opts.target → ${picked.label}`);
        setStampItem(null);
        setPreview(null);
        setPicked(null);
      } else if (result.errors > 0) {
        setError(result.results[0]?.message ?? 'Stamp failed');
      }
    } finally {
      setStampPending(false);
    }
  };

  const activeItem = activeKey ? byKey.get(activeKey) ?? null : null;

  return (
    <Card variant="outlined" id={CUSTOMER_TOKEN_SECTION_ID} sx={{ mb: 2 }} data-testid="customer-token-section">
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="h6">Customer-token stamp</Typography>
          <Typography variant="body2" color="text.secondary">
            Mint a global approved alias and stamp all lineup lines sharing the token. First live{' '}
            <code>opts.target</code> consumer on ResolutionWorklist.
          </Typography>

          {error ? (
            <Alert severity="error" onClose={() => setError(null)} data-testid="customer-token-error">
              {error}
            </Alert>
          ) : null}
          {conflictBanner ? (
            <Alert severity="warning" data-testid="customer-token-conflict-banner">
              <Typography variant="subtitle2">
                Genuine conflict for token “{conflictBanner.norm_token}” — stamp refused (no write).
              </Typography>
              <Typography variant="body2">
                Competing customers: {conflictBanner.competing_customer_ids.join(', ') || '—'}. Route via:{' '}
                {(conflictBanner.dispositions.length
                  ? conflictBanner.dispositions
                  : ['scoped', 'merge', 'data_error']
                ).map((d) => d.toUpperCase()).join(' · ')}
                . No inline override — use scoped alias, customer merge engine, or fix source data.
              </Typography>
            </Alert>
          ) : null}
          {success ? (
            <Alert severity="success" onClose={() => setSuccess(null)}>
              {success}
            </Alert>
          ) : null}

          <ResolutionWorklist<CustomerTokenWorkItem, BucketId>
            rootTestId="customer-token-worklist"
            items={filtered}
            getItemKey={(i) => i.item_key}
            buckets={buckets}
            activeBucket={bucket}
            onBucketChange={(id) => {
              setBucket(id);
              setSelected(new Set());
            }}
            selection={{
              selected,
              onToggle: (k) =>
                setSelected((prev) => {
                  const next = new Set(prev);
                  if (next.has(k)) next.delete(k);
                  else next.add(k);
                  return next;
                }),
              onReplace: (ks) => setSelected(new Set(ks)),
            }}
            applyAdapter={applyAdapter}
            actions={[
              {
                id: 'stamp',
                label: 'Stamp',
                requiresTarget: true,
                previewFirst: true,
                targets: (item) => item.alias_candidates,
                onRun: async ({ items: batch, target }) => {
                  const item = batch[0];
                  if (!item || !target) return;
                  await openStamp(item, target);
                },
              },
            ]}
            renderTargetPicker={({ item, targets, onPick }) => {
              if (item.bucket === 'empty_token') {
                return (
                  <Stack spacing={1} data-testid="customer-token-empty-picker">
                    <Alert severity="info" data-testid="customer-token-empty-hint">
                      Empty token · case {item.case_id ?? '—'} · {item.line_count} line(s). Stamps{' '}
                      <strong>customer_id only</strong> — no alias mint, no invented token. Ship/PO
                      customers are hints (explicit confirm required).
                      {item.sole_po_customer_count
                        ? ` · ${item.sole_po_customer_count} sole-customer PO(s)`
                        : ''}
                    </Alert>
                    <Typography variant="subtitle2">Pick customer target</Typography>
                    {targets.map((t) => (
                      <Button
                        key={t.targetKey}
                        size="small"
                        variant={picked?.targetKey === t.targetKey ? 'contained' : 'outlined'}
                        onClick={() => {
                          setPicked(t);
                          onPick(t);
                        }}
                        data-testid={`customer-token-empty-target-${t.targetKey}`}
                      >
                        {t.label}
                        {t.meta?.preferred ? ' · ship hint' : ''}
                        {t.meta?.is_open_channel ? ' · OPEN_CHANNEL' : ''}
                        {t.meta?.source ? ` · ${String(t.meta.source)}` : ''}
                      </Button>
                    ))}
                    <Stack direction="row" spacing={1} alignItems="center">
                      <TextField
                        size="small"
                        label="Free customer id"
                        value={freeTargetId}
                        onChange={(e) => setFreeTargetId(e.target.value)}
                        inputProps={{ 'data-testid': 'customer-token-empty-free-id' }}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        data-testid="customer-token-empty-free-apply"
                        onClick={() => {
                          const id = Number(freeTargetId);
                          if (!Number.isFinite(id) || id < 1) return;
                          const t: ResolutionTargetSelection = {
                            targetKey: String(id),
                            label: `customer:${id} (free pick)`,
                            meta: { customer_id: id, preferred: false },
                          };
                          setPicked(t);
                          onPick(t);
                        }}
                      >
                        Use free pick
                      </Button>
                    </Stack>
                  </Stack>
                );
              }
              if (item.conflict) {
                return (
                  <Alert severity="warning" data-testid="customer-token-row-conflict">
                    Genuine conflict — dispositions:{' '}
                    {(item.dispositions.length ? item.dispositions : ['scoped', 'merge', 'data_error'])
                      .map((d) => d.toUpperCase())
                      .join(' · ')}
                    . No stamp override.
                  </Alert>
                );
              }
              if (item.bucket === 'distributor_token' && item.distributor_token_match) {
                const oc =
                  targets.find((t) => t.meta?.is_open_channel) ??
                  ({
                    targetKey: String(worklistQ.data?.open_channel_customer_id ?? 1),
                    label: 'Open Channel',
                    meta: { is_open_channel: true, preferred: true },
                  } satisfies ResolutionTargetSelection);
                return (
                  <Stack spacing={1} data-testid="customer-token-distributor-picker">
                    <Alert severity="info">
                      Distributor token → Open Channel + distributor_id=
                      {item.distributor_token_match.distributor_id} (
                      {item.distributor_token_match.matched_via}:{' '}
                      {item.distributor_token_match.matched_key})
                      {item.would_set_attribution_status
                        ? ` · status=${item.would_set_attribution_status}`
                        : ''}
                    </Alert>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => {
                        setPicked(oc);
                        onPick(oc);
                      }}
                      data-testid="customer-token-target-open-channel"
                    >
                      Stamp as Open Channel
                    </Button>
                  </Stack>
                );
              }
              return (
                <Stack spacing={1} data-testid="customer-token-target-picker">
                  <Typography variant="subtitle2">Pick customer target</Typography>
                  {targets.map((t) => (
                    <Button
                      key={t.targetKey}
                      size="small"
                      variant={picked?.targetKey === t.targetKey ? 'contained' : 'outlined'}
                      onClick={() => {
                        setPicked(t);
                        onPick(t);
                      }}
                      data-testid={`customer-token-target-${t.targetKey}`}
                    >
                      {t.label}
                      {t.meta?.preferred ? ' · preferred' : ''}
                      {t.meta?.is_open_channel ? ' · OPEN_CHANNEL' : ''}
                      {t.meta?.source ? ` · ${String(t.meta.source)}` : ''}
                    </Button>
                  ))}
                  {item.free_target_allowed ? (
                    <Stack direction="row" spacing={1} alignItems="center">
                      <TextField
                        size="small"
                        label="Free customer id"
                        value={freeTargetId}
                        onChange={(e) => setFreeTargetId(e.target.value)}
                        inputProps={{ 'data-testid': 'customer-token-free-target-id' }}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        data-testid="customer-token-free-target-apply"
                        onClick={() => {
                          const id = Number(freeTargetId);
                          if (!Number.isFinite(id) || id < 1) return;
                          const t: ResolutionTargetSelection = {
                            targetKey: String(id),
                            label: `customer:${id} (free pick)`,
                            meta: { customer_id: id, preferred: false },
                          };
                          setPicked(t);
                          onPick(t);
                        }}
                      >
                        Use free pick
                      </Button>
                    </Stack>
                  ) : null}
                  {item.ship_corroboration_offer ? (
                    <Alert
                      severity="success"
                      data-testid={`customer-token-ship-offer-${item.item_key}`}
                      action={
                        <Button
                          color="inherit"
                          size="small"
                          data-testid={`customer-token-accept-ship-${item.item_key}`}
                          disabled={acceptShipMut.isPending}
                          onClick={() => {
                            acceptShipMut.mutate({
                              norm_token: item.norm_token,
                              distributor_id: item.ship_corroboration_offer!.distributor_id,
                              reason: 'steward accept ship-corroborated distributor',
                            });
                          }}
                        >
                          Accept OC + dist {item.ship_corroboration_offer.distributor_id}
                        </Button>
                      }
                    >
                      Ship corroboration: sole distributor{' '}
                      {item.ship_corroboration_offer.distributor_id} (
                      {item.ship_corroboration_offer.reason})
                    </Alert>
                  ) : null}
                </Stack>
              );
            }}
            renderRow={(item) => (
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                onClick={() => {
                  setActiveKey(item.item_key);
                  setPicked(preferredTarget(item));
                }}
                sx={{ cursor: 'pointer' }}
              >
                <Chip size="small" label={item.bucket} data-testid={`customer-token-bucket-${item.item_key}`} />
                {item.ship_corroboration_offer ? (
                  <Chip
                    size="small"
                    color="success"
                    label={`ship→${item.ship_corroboration_offer.distributor_id}`}
                    data-testid={`customer-token-ship-chip-${item.item_key}`}
                  />
                ) : null}
                <Typography variant="body2">
                  {item.sample_token || '(empty token)'} · {item.line_count} line(s)
                </Typography>
                {item.stamp_enabled ? (
                  <Button
                    size="small"
                    disabled={!picked && !preferredTarget(item)}
                    data-testid={`customer-token-stamp-${item.item_key}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      const t = picked?.targetKey ? picked : preferredTarget(item);
                      if (!t) return;
                      void openStamp(item, t);
                    }}
                  >
                    Stamp
                  </Button>
                ) : (
                  <Tooltip title="stamp refused">
                    <span>
                      <Button size="small" disabled data-testid={`customer-token-stamp-${item.item_key}`}>
                        Stamp
                      </Button>
                    </span>
                  </Tooltip>
                )}
              </Stack>
            )}
            drawer={{
              activeKey,
              onClose: () => setActiveKey(null),
              title: (item) => item.sample_token || item.norm_token || 'Empty token',
              renderEvidence: (item) => (
                <Stack spacing={1}>
                  <Typography variant="body2">Bucket: {item.bucket}</Typography>
                  <Typography variant="body2">Lines: {item.line_count}</Typography>
                  {item.conflict ? (
                    <Alert severity="warning" data-testid="customer-token-drawer-conflict">
                      Competing: {item.competing_customer_ids.join(', ')}. Dispositions:{' '}
                      {item.dispositions.map((d) => d.toUpperCase()).join(' · ')}.
                    </Alert>
                  ) : null}
                </Stack>
              ),
              renderDispositionActions: (item) =>
                item.stamp_enabled ? (
                  <Button
                    size="small"
                    variant="contained"
                    data-testid={`customer-token-drawer-stamp-${item.item_key}`}
                    onClick={() => {
                      const t = picked ?? preferredTarget(item);
                      if (t) void openStamp(item, t);
                    }}
                  >
                    Stamp with selected target
                  </Button>
                ) : null,
            }}
          />

          {(mintedQ.data?.aliases?.length ?? 0) > 0 ? (
            <Box data-testid="customer-token-minted-aliases">
              <Typography variant="subtitle1">Minted aliases</Typography>
              <Stack spacing={0.5}>
                {mintedQ.data!.aliases.map((a) => (
                  <Stack key={a.alias_id} direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2">
                      #{a.alias_id} {a.norm_token} → customer {a.customer_id} ({a.status})
                    </Typography>
                    {a.status === 'approved' ? (
                      <Button
                        size="small"
                        data-testid={`customer-token-revoke-${a.alias_id}`}
                        onClick={() => setRevokeAliasId(a.alias_id)}
                      >
                        Revoke
                      </Button>
                    ) : null}
                  </Stack>
                ))}
              </Stack>
            </Box>
          ) : null}
        </Stack>
      </CardContent>

      <Dialog
        open={!!stampItem && !!preview}
        onClose={() => {
          setStampItem(null);
          setPreview(null);
        }}
        data-testid="customer-token-stamp-dialog"
      >
        <DialogTitle>Confirm stamp</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            <Typography variant="body2" data-testid="customer-token-preview-blast">
              Blast radius: {preview?.line_count ?? 0} line(s) → {preview?.target_customer_label}
              {stampItem?.tokenless || stampItem?.bucket === 'empty_token'
                ? ' (tokenless — customer_id only, no alias)'
                : preview?.would_create_alias
                  ? ' (will create global alias)'
                  : ' (reuse existing alias)'}
            </Typography>
            {stampItem?.tokenless || stampItem?.bucket === 'empty_token' ? (
              <Typography variant="caption" color="text.secondary" data-testid="customer-token-tokenless-preview">
                Cases: {(preview?.case_ids ?? []).join(', ') || '—'} · rejected:{' '}
                {preview?.rejected_count ?? 0}
              </Typography>
            ) : (
              <Typography variant="caption" color="text.secondary">
                Breakdown: {JSON.stringify(preview?.current_resolution_breakdown ?? {})}
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary" data-testid="customer-token-opts-target">
              opts.target.targetKey = {picked?.targetKey ?? '—'}
            </Typography>
            <TextField
              label="Reason"
              size="small"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              inputProps={{ 'data-testid': 'customer-token-stamp-reason' } as InputHTMLAttributes<HTMLInputElement>}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setStampItem(null); setPreview(null); }}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!reason.trim() || stampPending}
            onClick={() => void confirmStamp()}
            data-testid="customer-token-stamp-submit"
          >
            Confirm stamp
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={revokeAliasId != null} onClose={() => setRevokeAliasId(null)}>
        <DialogTitle>Revoke alias</DialogTitle>
        <DialogContent>
          <TextField
            label="Reason"
            size="small"
            fullWidth
            sx={{ mt: 1 }}
            value={revokeReason}
            onChange={(e) => setRevokeReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevokeAliasId(null)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            data-testid="customer-token-revoke-submit"
            onClick={() => {
              if (revokeAliasId == null) return;
              revokeMut.mutate({ alias_id: revokeAliasId, reason: revokeReason });
            }}
          >
            Confirm revoke
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

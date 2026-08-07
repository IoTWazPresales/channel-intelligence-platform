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
  bucket: 'clean' | 'specificity' | 'genuine_conflict' | 'empty_token' | string;
  alias_candidates: ResolutionTargetSelection[];
  preferred_target_id: number | null;
  stamp_enabled: boolean;
  conflict: boolean;
  competing_customer_ids: number[];
  dispositions: string[];
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
  current_resolution_breakdown: Record<string, number>;
  would_create_alias: boolean;
  sample_lines: Array<{ line_id: number; case_id: number; customer_id: number | null }>;
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

type BucketId = 'all' | 'clean' | 'specificity' | 'genuine_conflict' | 'empty_token';

function preferredTarget(item: CustomerTokenWorkItem): ResolutionTargetSelection | null {
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
      { id: 'genuine_conflict', label: 'Conflict', count: c.genuine_conflict ?? 0 },
      { id: 'empty_token', label: 'Empty token', count: c.empty_token ?? 0 },
    ];
  }, [worklistQ.data?.bucket_counts, items.length]);

  const previewMut = useMutation({
    mutationFn: (vars: { norm_token: string; target_customer_id: number }) =>
      apiPost<PreviewResponse>('/api/v1/commercial-planner/lineup/customer-token/stamp/preview', vars),
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
          await apiPost<ApplyResponse>('/api/v1/commercial-planner/lineup/customer-token/stamp/apply', {
            norm_token: item.norm_token,
            target_customer_id: targetCustomerId,
            reason,
          });
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
    const prev = await previewMut.mutateAsync({
      norm_token: item.norm_token,
      target_customer_id: Number(target.targetKey),
    });
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
                  <Typography variant="body2" color="text.secondary" data-testid="customer-token-empty-hint">
                    No token — see backlog tokenless acquisition. Stamp disabled.
                  </Typography>
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
                    </Button>
                  ))}
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
                  <Tooltip title={item.bucket === 'empty_token' ? 'no token — see backlog' : 'stamp refused'}>
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
              {preview?.would_create_alias ? ' (will create global alias)' : ' (reuse existing alias)'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Breakdown: {JSON.stringify(preview?.current_resolution_breakdown ?? {})}
            </Typography>
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

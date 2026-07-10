'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ReferenceCount = { label: string; count: number };

type AliasScopeMember = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  created_at: string | null;
  survivor_hint: boolean;
  verified: boolean;
  merged_into_customer_id: number | null;
  reference_counts: ReferenceCount[];
};

type AliasScopeGroup = {
  conflict_key: string;
  scope: {
    normalized_token: string;
    source_definition_id: number | null;
    distributor_id: number | null;
  };
  member_count: number;
  alias_rows: number;
  token_variants?: string[];
  members: AliasScopeMember[];
  default_survivor_id: number | null;
};

type AliasScopeResponse = {
  items: AliasScopeGroup[];
  page: number;
  page_size: number;
  total: number;
};

const DEFAULT_PAGE_SIZE = 25;

function totalRefs(counts: ReferenceCount[]): number {
  return counts.reduce((sum, r) => sum + (r.count ?? 0), 0);
}

function mergePayloadForGroup(
  group: AliasScopeGroup,
  survivorId: number,
  auditNote: string,
  returnJobId: string
): Record<string, unknown> {
  return {
    normalized_token: group.scope.normalized_token,
    source_definition_id: group.scope.source_definition_id,
    distributor_id: group.scope.distributor_id,
    survivor_id: survivorId,
    audit_note: auditNote,
    return_import_job_id: returnJobId ? Number(returnJobId) : null,
  };
}

export function AliasScopeConflictsSection() {
  const searchParams = useSearchParams();
  const tokenFilter = searchParams.get('token') ?? '';
  const returnJobId = searchParams.get('return_job') ?? searchParams.get('job') ?? '';
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [survivorByGroup, setSurvivorByGroup] = useState<Record<string, number>>({});
  const [mergeGroup, setMergeGroup] = useState<AliasScopeGroup | null>(null);
  const [auditNote, setAuditNote] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-customer-alias-scope-conflicts', page, pageSize, tokenFilter],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      if (tokenFilter) sp.set('normalized_token', tokenFilter);
      return apiGet<AliasScopeResponse>(`/api/v1/customers/alias-scope-conflicts?${sp.toString()}`, { signal });
    },
  });

  const groups = useMemo(() => data?.items ?? [], [data?.items]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setSurvivorByGroup((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of groups) {
        if (next[g.conflict_key] == null && g.default_survivor_id != null) {
          next[g.conflict_key] = g.default_survivor_id;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [groups]);

  const previewMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<Record<string, unknown>>('/api/v1/customers/alias-scope-conflicts/merge-preview', body),
    onSuccess: (res) => setPreview(res),
  });

  const confirmMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<{ task_id: string; async_poll: boolean; revalidate_href?: string }>(
        '/api/v1/customers/alias-scope-conflicts/merge-confirm',
        body
      ),
  });

  const pollMergeTask = useCallback(async (taskId: string) => {
    for (let i = 0; i < 120; i++) {
      const res = await apiGet<{ state: string; result?: Record<string, unknown>; error?: string }>(
        `/api/v1/customers/alias-scope-conflicts/merge-task/${taskId}`
      );
      if (res.state === 'SUCCESS') return res;
      if (res.state === 'FAILURE') throw new Error(res.error || 'Merge failed');
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw new Error('Merge timed out');
  }, []);

  const runSingleMerge = useCallback(
    async (group: AliasScopeGroup, survivorId: number, note: string) => {
      const body = mergePayloadForGroup(group, survivorId, note, returnJobId);
      const queued = await confirmMutation.mutateAsync(body);
      if (queued.task_id) await pollMergeTask(queued.task_id);
    },
    [confirmMutation, pollMergeTask, returnJobId]
  );

  const openMergeDialog = (group: AliasScopeGroup) => {
    setMergeGroup(group);
    setAuditNote('');
    setPreview(null);
  };

  const survivorForGroup = (group: AliasScopeGroup): number | null =>
    survivorByGroup[group.conflict_key] ?? group.default_survivor_id;

  const mergeBody = useMemo(() => {
    if (!mergeGroup) return null;
    const sid = survivorForGroup(mergeGroup);
    if (sid == null) return null;
    return mergePayloadForGroup(mergeGroup, sid, auditNote, returnJobId);
  }, [auditNote, mergeGroup, returnJobId, survivorByGroup]);

  const runBulkMerge = async () => {
    if (!auditNote.trim() || groups.length === 0) return;
    setBulkError(null);
    setBulkProgress(`0 / ${groups.length}`);
    try {
      for (let i = 0; i < groups.length; i++) {
        const g = groups[i];
        const sid = survivorForGroup(g);
        if (sid == null) continue;
        setBulkProgress(`${i + 1} / ${groups.length}: ${g.scope.normalized_token}`);
        await runSingleMerge(g, sid, auditNote.trim());
      }
      setBulkOpen(false);
      setAuditNote('');
      void queryClient.invalidateQueries({ queryKey: ['admin-customer-alias-scope-conflicts'] });
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : 'Bulk merge failed');
    } finally {
      setBulkProgress(null);
    }
  };

  return (
    <>
      <Alert severity="success" variant="outlined" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Merge workflow (closes DSI master-data alias conflicts)
        </Typography>
        <Typography component="ol" variant="body2" sx={{ m: 0, pl: 2.5 }}>
          <li>Select the <strong>survivor</strong> customer per group (radio). Hint = verified, then oldest.</li>
          <li>Click <strong>Merge this group</strong> (or bulk below) → enter audit note → <strong>Preview</strong> → <strong>Confirm merge</strong>.</li>
          <li>
            {returnJobId ? (
              <>
                Return to{' '}
                <Link href={`/admin/imports?job=${encodeURIComponent(returnJobId)}`}>DSI job #{returnJobId}</Link> and{' '}
                <strong>Revalidate</strong>.
              </>
            ) : (
              <>Then <strong>Revalidate</strong> your DSI import job.</>
            )}
          </li>
        </Typography>
      </Alert>
      {returnJobId ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Opened from DSI job #{returnJobId}. After all merges here, revalidate that job before Apply.
        </Alert>
      ) : null}
      {tokenFilter ? (
        <Chip
          label={`Token filter: ${tokenFilter}`}
          sx={{ mb: 2 }}
          onDelete={() => {
            window.location.href = '/admin/customers/duplicates?tab=alias_scope&page=1&page_size=25';
          }}
        />
      ) : null}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button component={Link} href="/admin/customers" variant="outlined">
          Back to customers
        </Button>
        <ModuleGridToolbar onRefresh={() => void refetch()} sx={{ mb: 0 }} />
        <Button
          variant="contained"
          disabled={groups.length === 0 || Boolean(bulkProgress)}
          onClick={() => {
            setAuditNote('');
            setBulkError(null);
            setBulkOpen(true);
          }}
        >
          Bulk merge this page ({groups.length})
        </Button>
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              <strong>{total}</strong> alias-scope conflict group{total === 1 ? '' : 's'} — same approved alias token
              maps to more than one customer.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && groups.length === 0}
          empty={{
            title: 'No alias-scope conflicts',
            description:
              'No approved alias scope maps to multiple customers. If DSI still shows master-data conflicts, revalidate the job or check the token filter.',
            primary: returnJobId
              ? { label: `Back to DSI job #${returnJobId}`, href: `/admin/imports?job=${returnJobId}` }
              : { label: 'Import Center', href: '/admin/imports' },
          }}
        >
          <Stack spacing={3}>
            {groups.map((group) => {
              const selectedSurvivor = survivorForGroup(group);
              return (
                <Paper key={group.conflict_key} variant="outlined" sx={{ p: 2 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                    <Typography variant="subtitle1">Token: {group.scope.normalized_token}</Typography>
                    <Chip size="small" label={`${group.member_count} customers`} />
                    <Chip size="small" variant="outlined" label={`${group.alias_rows} alias rows`} />
                    {(group.token_variants?.length ?? 0) > 1 ? (
                      <Chip
                        size="small"
                        variant="outlined"
                        color="warning"
                        label={`${group.token_variants?.length ?? 0} spelling variants`}
                      />
                    ) : null}
                    <Button
                      size="small"
                      variant="contained"
                      disabled={selectedSurvivor == null || Boolean(bulkProgress)}
                      onClick={() => openMergeDialog(group)}
                    >
                      Merge this group
                    </Button>
                  </Stack>
                  {(group.token_variants?.length ?? 0) > 1 ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                      DB spellings: {group.token_variants?.join(' · ')}
                    </Typography>
                  ) : null}
                  <FormControl component="fieldset" sx={{ mb: 1.5, width: '100%' }}>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                      Survivor (keeper) — losers are soft-redirected
                    </Typography>
                    <RadioGroup
                      value={selectedSurvivor != null ? String(selectedSurvivor) : ''}
                      onChange={(e) =>
                        setSurvivorByGroup((prev) => ({
                          ...prev,
                          [group.conflict_key]: Number(e.target.value),
                        }))
                      }
                    >
                      {group.members.map((m) => (
                        <FormControlLabel
                          key={m.id}
                          value={String(m.id)}
                          control={<Radio size="small" />}
                          label={
                            <Typography variant="body2">
                              {m.customer_code} — {m.customer_name}
                              {m.survivor_hint ? ' (hint)' : ''}
                              {m.merged_into_customer_id ? ` · merged→${m.merged_into_customer_id}` : ''}
                              {' · '}
                              {m.customer_status}
                              {' · FK '}
                              {totalRefs(m.reference_counts)}
                            </Typography>
                          }
                        />
                      ))}
                    </RadioGroup>
                  </FormControl>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Code</TableCell>
                          <TableCell>Name</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell align="right">FK rows</TableCell>
                          <TableCell>References</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {group.members.map((m) => (
                          <TableRow key={m.id} selected={m.id === selectedSurvivor}>
                            <TableCell>{m.customer_code}</TableCell>
                            <TableCell>{m.customer_name}</TableCell>
                            <TableCell>{m.customer_status}</TableCell>
                            <TableCell align="right">{totalRefs(m.reference_counts)}</TableCell>
                            <TableCell>
                              {m.reference_counts.length === 0 ? (
                                '—'
                              ) : (
                                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                                  {m.reference_counts.map((ref) => (
                                    <Typography key={`${ref.label}-${ref.count}`} component="li" variant="body2">
                                      {ref.label}: {ref.count}
                                    </Typography>
                                  ))}
                                </Box>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              );
            })}
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 3 }} alignItems="center">
            <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Prev
            </Button>
            <Typography variant="body2">
              Page {page} / {totalPages}
            </Typography>
            <Button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Page size</InputLabel>
              <Select label="Page size" value={String(pageSize)} onChange={(e) => setPageSize(Number(e.target.value))}>
                <MenuItem value="10">10</MenuItem>
                <MenuItem value="25">25</MenuItem>
                <MenuItem value="50">50</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </ModuleDataSection>
      </Paper>

      <Dialog open={mergeGroup !== null} onClose={() => setMergeGroup(null)} maxWidth="md" fullWidth>
        <DialogTitle>Merge alias-scope conflict</DialogTitle>
        <DialogContent>
          {mergeGroup ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Token <strong>{mergeGroup.scope.normalized_token}</strong> · survivor{' '}
                <strong>{survivorForGroup(mergeGroup) ?? '—'}</strong>
              </Typography>
              <TextField
                label="Audit note (required)"
                value={auditNote}
                onChange={(e) => setAuditNote(e.target.value)}
                multiline
                minRows={2}
                fullWidth
                required
                helperText="Why these customers are being merged (steward record)."
              />
              {preview ? (
                <Box
                  component="pre"
                  sx={{ fontSize: 12, overflow: 'auto', maxHeight: 240, bgcolor: 'action.hover', p: 1 }}
                >
                  {JSON.stringify(preview, null, 2)}
                </Box>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMergeGroup(null)}>Cancel</Button>
          <Button
            disabled={!auditNote.trim() || previewMutation.isPending || !mergeBody}
            onClick={() => mergeBody && previewMutation.mutate(mergeBody)}
          >
            Preview FK repoint
          </Button>
          <Button
            variant="contained"
            disabled={!auditNote.trim() || !preview || confirmMutation.isPending}
            onClick={async () => {
              if (!mergeGroup || !mergeBody) return;
              const sid = survivorForGroup(mergeGroup);
              if (sid == null) return;
              try {
                await runSingleMerge(mergeGroup, sid, auditNote.trim());
                setMergeGroup(null);
                setPreview(null);
                void queryClient.invalidateQueries({ queryKey: ['admin-customer-alias-scope-conflicts'] });
              } catch (err) {
                console.error(err);
              }
            }}
          >
            Confirm merge
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkOpen} onClose={() => !bulkProgress && setBulkOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Bulk merge — this page</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Merges <strong>{groups.length}</strong> group(s) using each group&apos;s selected survivor (hint
              default). Runs sequentially; same audit note for all.
            </Typography>
            <TextField
              label="Audit note (required)"
              value={auditNote}
              onChange={(e) => setAuditNote(e.target.value)}
              multiline
              minRows={2}
              fullWidth
              disabled={Boolean(bulkProgress)}
            />
            {bulkProgress ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={20} />
                <Typography variant="body2">{bulkProgress}</Typography>
              </Stack>
            ) : null}
            {bulkError ? (
              <Alert severity="error" onClose={() => setBulkError(null)}>
                {bulkError}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={Boolean(bulkProgress)} onClick={() => setBulkOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!auditNote.trim() || Boolean(bulkProgress)}
            onClick={() => void runBulkMerge()}
          >
            Merge all on page
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

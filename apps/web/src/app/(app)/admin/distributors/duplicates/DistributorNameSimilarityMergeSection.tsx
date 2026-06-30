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
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ReferenceCount = { label: string; count: number };

type DuplicateMember = {
  id: number;
  distributor_code: string;
  distributor_name: string;
  distributor_status: string;
  created_at: string | null;
  survivor_hint: boolean;
  reference_counts: ReferenceCount[];
};

type DuplicateGroup = {
  similarity_key: string;
  member_count: number;
  members: DuplicateMember[];
};

type DuplicateGroupsResponse = {
  items: DuplicateGroup[];
  page: number;
  page_size: number;
  total: number;
  distributors_scanned: number;
};

function totalRefs(counts: ReferenceCount[]): number {
  return counts.reduce((sum, r) => sum + (r.count ?? 0), 0);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return value;
  }
}

function mergePayloadForGroup(
  group: DuplicateGroup,
  survivorId: number,
  auditNote: string
): Record<string, unknown> {
  return {
    similarity_key: group.similarity_key,
    distributor_ids: group.members.map((m) => m.id),
    survivor_id: survivorId,
    audit_note: auditNote,
  };
}

type DistributorNameSimilarityMergeSectionProps = {
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

export function DistributorNameSimilarityMergeSection({
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: DistributorNameSimilarityMergeSectionProps) {
  const queryClient = useQueryClient();
  const [survivorByGroup, setSurvivorByGroup] = useState<Record<string, number>>({});
  const [mergeGroup, setMergeGroup] = useState<DuplicateGroup | null>(null);
  const [auditNote, setAuditNote] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPreview, setBulkPreview] = useState<Record<string, unknown> | null>(null);
  const [bulkProgress, setBulkProgress] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-distributor-duplicate-groups', page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      return apiGet<DuplicateGroupsResponse>(`/api/v1/distributors/duplicate-groups?${sp.toString()}`, { signal });
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
        const hint = g.members.find((m) => m.survivor_hint);
        if (next[g.similarity_key] == null && hint != null) {
          next[g.similarity_key] = hint.id;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [groups]);

  const previewMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<Record<string, unknown>>('/api/v1/distributors/duplicate-groups/merge-preview', body),
    onSuccess: (res) => setPreview(res),
  });

  const bulkPreviewMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<Record<string, unknown>>('/api/v1/distributors/duplicate-groups/merge-preview-bulk', body),
    onSuccess: (res) => setBulkPreview(res),
  });

  const confirmMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<{ task_id: string; async_poll: boolean }>('/api/v1/distributors/duplicate-groups/merge-confirm', body),
  });

  const pollMergeTask = useCallback(async (taskId: string) => {
    for (let i = 0; i < 120; i++) {
      const res = await apiGet<{ state: string; result?: Record<string, unknown>; error?: string }>(
        `/api/v1/distributors/duplicate-groups/merge-task/${taskId}`
      );
      if (res.state === 'SUCCESS') return res;
      if (res.state === 'FAILURE') throw new Error(res.error || 'Merge failed');
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw new Error('Merge timed out');
  }, []);

  const runSingleMerge = useCallback(
    async (group: DuplicateGroup, survivorId: number, note: string) => {
      const body = mergePayloadForGroup(group, survivorId, note);
      const queued = await confirmMutation.mutateAsync(body);
      if (queued.task_id) await pollMergeTask(queued.task_id);
    },
    [confirmMutation, pollMergeTask]
  );

  const openMergeDialog = (group: DuplicateGroup) => {
    setMergeGroup(group);
    setAuditNote('');
    setPreview(null);
  };

  const survivorForGroup = (group: DuplicateGroup): number | null =>
    survivorByGroup[group.similarity_key] ?? group.members.find((m) => m.survivor_hint)?.id ?? null;

  const mergeBody = useMemo(() => {
    if (!mergeGroup) return null;
    const sid = survivorForGroup(mergeGroup);
    if (sid == null) return null;
    return mergePayloadForGroup(mergeGroup, sid, auditNote);
  }, [auditNote, mergeGroup, survivorByGroup]);

  const bulkGroupsPayload = useMemo(
    () =>
      groups
        .map((g) => {
          const sid = survivorForGroup(g);
          if (sid == null) return null;
          return {
            similarity_key: g.similarity_key,
            survivor_id: sid,
            distributor_ids: g.members.map((m) => m.id),
          };
        })
        .filter(Boolean),
    [groups, survivorByGroup]
  );

  const runBulkMerge = async () => {
    if (!auditNote.trim() || groups.length === 0 || !bulkPreview) return;
    setBulkError(null);
    setBulkProgress(`0 / ${groups.length}`);
    try {
      for (let i = 0; i < groups.length; i++) {
        const g = groups[i];
        const sid = survivorForGroup(g);
        if (sid == null) continue;
        setBulkProgress(`${i + 1} / ${groups.length}: ${g.similarity_key}`);
        await runSingleMerge(g, sid, auditNote.trim());
      }
      setBulkOpen(false);
      setBulkPreview(null);
      setAuditNote('');
      void queryClient.invalidateQueries({ queryKey: ['admin-distributor-duplicate-groups'] });
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : 'Bulk merge failed');
    } finally {
      setBulkProgress(null);
    }
  };

  return (
    <>
      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Full distributor merge (name-similarity groups)
        </Typography>
        <Typography component="ol" variant="body2" sx={{ m: 0, pl: 2.5 }}>
          <li>Select the <strong>survivor</strong> per group (non-provisional verified, then oldest). ZA legal-form flags are advisory only.</li>
          <li>
            <strong>Merge this group</strong> or <strong>Bulk merge this page</strong> → audit note → <strong>Preview</strong> (includes PO
            consolidation plan) → <strong>Confirm merge</strong>.
          </li>
          <li>
            Losers are soft-redirected (<code>merged_into_distributor_id</code>). Colliding PO numbers consolidate into the survivor&apos;s PO row.
          </li>
        </Typography>
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button component={Link} href="/admin/distributors" variant="outlined">
          Back to distributors
        </Button>
        <ModuleGridToolbar onRefresh={() => void refetch()} sx={{ mb: 0 }} />
        <Button
          variant="contained"
          disabled={groups.length === 0 || Boolean(bulkProgress)}
          onClick={() => {
            setAuditNote('');
            setBulkError(null);
            setBulkPreview(null);
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
              Scanned <strong>{data?.distributors_scanned ?? '…'}</strong> distributors;{' '}
              <strong>{total}</strong> duplicate group{total === 1 ? '' : 's'} with 2+ members (merged tombstones excluded).
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && groups.length === 0}
          empty={{
            title: 'No duplicate groups found',
            description: 'No distributors share the same similarity-normalised name key with at least one other member.',
            primary: { label: 'Distributor master', href: '/admin/distributors' },
          }}
        >
          <Stack spacing={3}>
            {groups.map((group) => {
              const selectedSurvivor = survivorForGroup(group);
              const ambiguous = group.members.some(
                (m, _i, arr) =>
                  arr.length > 1 &&
                  /pty|ltd|cc/i.test(m.distributor_name) &&
                  new Set(arr.map((x) => x.distributor_name.toLowerCase())).size > 1
              );
              return (
                <Paper key={group.similarity_key} variant="outlined" sx={{ p: 2 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                    <Typography variant="subtitle1">Group: {group.similarity_key}</Typography>
                    <Chip size="small" label={`${group.member_count} members`} />
                    {ambiguous ? (
                      <Chip size="small" color="warning" variant="outlined" label="Review survivor — ZA legal-form variants" />
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
                  <FormControl component="fieldset" sx={{ mb: 1.5, width: '100%' }}>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                      Survivor (keeper) — losers are soft-redirected
                    </Typography>
                    <RadioGroup
                      value={selectedSurvivor != null ? String(selectedSurvivor) : ''}
                      onChange={(e) =>
                        setSurvivorByGroup((prev) => ({
                          ...prev,
                          [group.similarity_key]: Number(e.target.value),
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
                              {m.distributor_code} — {m.distributor_name}
                              {m.survivor_hint ? ' (hint)' : ''}
                              {' · '}
                              {m.distributor_status}
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
                          <TableCell>Created</TableCell>
                          <TableCell align="right">FK rows</TableCell>
                          <TableCell>References</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {group.members.map((m) => (
                          <TableRow key={m.id} selected={m.id === selectedSurvivor}>
                            <TableCell>{m.distributor_code}</TableCell>
                            <TableCell>{m.distributor_name}</TableCell>
                            <TableCell>{m.distributor_status}</TableCell>
                            <TableCell>{formatDateTime(m.created_at)}</TableCell>
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
            <Button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
              Prev
            </Button>
            <Typography variant="body2">
              Page {page} / {totalPages} ({total} groups)
            </Typography>
            <Button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
              Next
            </Button>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Page size</InputLabel>
              <Select
                label="Page size"
                value={String(pageSize)}
                onChange={(e) => onPageSizeChange(Number(e.target.value))}
              >
                <MenuItem value="10">10</MenuItem>
                <MenuItem value="25">25</MenuItem>
                <MenuItem value="50">50</MenuItem>
                <MenuItem value="100">100</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </ModuleDataSection>
      </Paper>

      <Dialog open={mergeGroup !== null} onClose={() => setMergeGroup(null)} maxWidth="md" fullWidth>
        <DialogTitle>Merge duplicate distributors</DialogTitle>
        <DialogContent>
          {mergeGroup ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Group <strong>{mergeGroup.similarity_key}</strong> · survivor{' '}
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
              />
              {preview ? (
                <Box
                  component="pre"
                  sx={{ fontSize: 12, overflow: 'auto', maxHeight: 280, bgcolor: 'action.hover', p: 1 }}
                  data-testid="distributor-merge-preview-json"
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
            Preview FK + PO plan
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
                void queryClient.invalidateQueries({ queryKey: ['admin-distributor-duplicate-groups'] });
              } catch (err) {
                console.error(err);
              }
            }}
          >
            Confirm merge
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkOpen} onClose={() => !bulkProgress && setBulkOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Bulk merge — this page</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Merges <strong>{groups.length}</strong> group(s) using each group&apos;s selected survivor.
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
            {bulkPreview ? (
              <Box
                component="pre"
                sx={{ fontSize: 12, overflow: 'auto', maxHeight: 280, bgcolor: 'action.hover', p: 1 }}
              >
                {JSON.stringify(bulkPreview, null, 2)}
              </Box>
            ) : null}
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
            disabled={!auditNote.trim() || bulkPreviewMutation.isPending || bulkGroupsPayload.length === 0}
            onClick={() =>
              bulkPreviewMutation.mutate({
                audit_note: auditNote.trim(),
                groups: bulkGroupsPayload,
              })
            }
          >
            Preview aggregate
          </Button>
          <Button
            variant="contained"
            disabled={!auditNote.trim() || !bulkPreview || Boolean(bulkProgress)}
            onClick={() => void runBulkMerge()}
          >
            Confirm merge all
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

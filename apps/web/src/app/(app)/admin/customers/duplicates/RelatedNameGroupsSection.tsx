'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
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

type RelatedMember = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  created_at: string | null;
  survivor_hint: boolean;
  reference_counts: ReferenceCount[];
  match_basis: 'anchor' | 'contained_prefix' | 'root_similarity' | string;
  score: number;
};

type RelatedGroup = {
  anchor_similarity_key: string;
  member_count: number;
  members: RelatedMember[];
};

type RelatedGroupsResponse = {
  items: RelatedGroup[];
  page: number;
  page_size: number;
  total: number;
  customers_scanned: number;
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

function basisLabel(basis: string): string {
  if (basis === 'anchor') return 'anchor';
  if (basis === 'contained_prefix') return 'contained prefix';
  if (basis === 'root_similarity') return 'similar root';
  return basis;
}

function mergePayloadForSelection(
  group: RelatedGroup,
  selectedIds: number[],
  survivorId: number,
  auditNote: string
): Record<string, unknown> {
  return {
    similarity_key: `related:${group.anchor_similarity_key}`,
    customer_ids: selectedIds,
    survivor_id: survivorId,
    audit_note: auditNote,
  };
}

type RelatedNameGroupsSectionProps = {
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

export function RelatedNameGroupsSection({
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: RelatedNameGroupsSectionProps) {
  const queryClient = useQueryClient();
  const [selectedByGroup, setSelectedByGroup] = useState<Record<string, number[]>>({});
  const [survivorByGroup, setSurvivorByGroup] = useState<Record<string, number>>({});
  const [mergeGroup, setMergeGroup] = useState<RelatedGroup | null>(null);
  const [auditNote, setAuditNote] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [mergeError, setMergeError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-customer-related-groups', page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      return apiGet<RelatedGroupsResponse>(`/api/v1/customers/duplicate-groups/related?${sp.toString()}`, {
        signal,
      });
    },
  });

  const groups = useMemo(() => data?.items ?? [], [data?.items]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setSelectedByGroup((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of groups) {
        if (next[g.anchor_similarity_key] == null) {
          const anchor = g.members.find((m) => m.match_basis === 'anchor') ?? g.members[0];
          next[g.anchor_similarity_key] = anchor ? [anchor.id] : [];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    setSurvivorByGroup((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of groups) {
        if (next[g.anchor_similarity_key] == null) {
          const hint = g.members.find((m) => m.survivor_hint) ?? g.members[0];
          if (hint) {
            next[g.anchor_similarity_key] = hint.id;
            changed = true;
          }
        }
      }
      return changed ? next : prev;
    });
  }, [groups]);

  const previewMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<Record<string, unknown>>('/api/v1/customers/duplicate-groups/merge-preview', body),
    onSuccess: (res) => {
      setPreview(res);
      setMergeError(null);
    },
    onError: (err) => {
      setMergeError(err instanceof Error ? err.message : 'Preview failed');
      setPreview(null);
      void refetch();
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<{ task_id: string; async_poll: boolean }>('/api/v1/customers/duplicate-groups/merge-confirm', body),
  });

  const pollMergeTask = useCallback(async (taskId: string) => {
    for (let i = 0; i < 120; i++) {
      const res = await apiGet<{ state: string; result?: Record<string, unknown>; error?: string }>(
        `/api/v1/customers/duplicate-groups/merge-task/${taskId}`
      );
      if (res.state === 'SUCCESS') return res;
      if (res.state === 'FAILURE') throw new Error(res.error || 'Merge failed');
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw new Error('Merge timed out');
  }, []);

  const selectedFor = (group: RelatedGroup): number[] =>
    selectedByGroup[group.anchor_similarity_key] ??
    (group.members.find((m) => m.match_basis === 'anchor')
      ? [group.members.find((m) => m.match_basis === 'anchor')!.id]
      : []);

  const survivorForGroup = (group: RelatedGroup): number | null => {
    const selected = selectedFor(group);
    const current = survivorByGroup[group.anchor_similarity_key];
    if (current != null && selected.includes(current)) return current;
    const hint = group.members.find((m) => m.survivor_hint && selected.includes(m.id));
    return hint?.id ?? selected[0] ?? null;
  };

  const toggleMember = (group: RelatedGroup, memberId: number, checked: boolean) => {
    const key = group.anchor_similarity_key;
    setSelectedByGroup((prev) => {
      const current = new Set(prev[key] ?? []);
      if (checked) current.add(memberId);
      else current.delete(memberId);
      return { ...prev, [key]: [...current] };
    });
  };

  const openMergeDialog = (group: RelatedGroup) => {
    setMergeGroup(group);
    setAuditNote('');
    setPreview(null);
    setMergeError(null);
  };

  const mergeBody = useMemo(() => {
    if (!mergeGroup) return null;
    const selected = selectedFor(mergeGroup);
    const sid = survivorForGroup(mergeGroup);
    if (sid == null || selected.length < 2) return null;
    return mergePayloadForSelection(mergeGroup, selected, sid, auditNote);
  }, [auditNote, mergeGroup, selectedByGroup, survivorByGroup]);

  const clearGroupSelection = (anchorKey: string) => {
    setSelectedByGroup((prev) => {
      const next = { ...prev };
      delete next[anchorKey];
      return next;
    });
  };

  return (
    <>
      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Related names — review before merge
        </Typography>
        <Typography variant="body2">
          Candidates may be different entities. Check only the members that are the same customer, choose a survivor,
          then preview → confirm. Losers are soft-redirected (<code>merged_into_customer_id</code>). This tab is not
          tied to an import job — no revalidate/recommit bounce.
        </Typography>
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button component={Link} href="/admin/customers" variant="outlined">
          Back to customers
        </Button>
        <ModuleGridToolbar onRefresh={() => void refetch()} sx={{ mb: 0 }} />
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Scanned <strong>{data?.customers_scanned ?? '…'}</strong> customers; <strong>{total}</strong> related
              group{total === 1 ? '' : 's'} (anchor + candidates).
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && groups.length === 0}
          empty={{
            title: 'No related-name groups found',
            description:
              'No eligible anchors with token-prefix or root-similarity candidates. Exact-name duplicates stay on the name-similarity tab.',
            primary: { label: 'Customer master', href: '/admin/customers' },
          }}
        >
          <Stack spacing={3}>
            {groups.map((group) => {
              const selected = selectedFor(group);
              const selectedSurvivor = survivorForGroup(group);
              const canMerge = selected.length >= 2 && selectedSurvivor != null;
              return (
                <Paper key={group.anchor_similarity_key} variant="outlined" sx={{ p: 2 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                    <Typography variant="subtitle1">Anchor: {group.anchor_similarity_key}</Typography>
                    <Chip size="small" label={`${group.member_count} members`} />
                    <Chip size="small" variant="outlined" label={`${selected.length} selected`} />
                    <Button
                      size="small"
                      variant="contained"
                      disabled={!canMerge}
                      onClick={() => openMergeDialog(group)}
                      data-testid={`merge-related-${group.anchor_similarity_key}`}
                    >
                      Merge selected
                    </Button>
                  </Stack>
                  <FormControl component="fieldset" sx={{ mb: 1.5, width: '100%' }}>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                      Survivor (keeper) — only among checked members
                    </Typography>
                    <RadioGroup
                      value={selectedSurvivor != null ? String(selectedSurvivor) : ''}
                      onChange={(e) =>
                        setSurvivorByGroup((prev) => ({
                          ...prev,
                          [group.anchor_similarity_key]: Number(e.target.value),
                        }))
                      }
                    >
                      {group.members.map((m) => {
                        const checked = selected.includes(m.id);
                        return (
                          <Stack
                            key={m.id}
                            direction="row"
                            spacing={1}
                            alignItems="center"
                            sx={{ opacity: checked ? 1 : 0.7 }}
                          >
                            <Checkbox
                              size="small"
                              checked={checked}
                              onChange={(e) => toggleMember(group, m.id, e.target.checked)}
                              inputProps={{ 'aria-label': `Select ${m.customer_code}` }}
                            />
                            <FormControlLabel
                              value={String(m.id)}
                              disabled={!checked}
                              control={<Radio size="small" />}
                              label={
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                  <Typography variant="body2">
                                    {m.customer_code} — {m.customer_name}
                                    {m.survivor_hint ? ' (hint)' : ''}
                                    {' · '}
                                    {m.customer_status}
                                    {' · FK '}
                                    {totalRefs(m.reference_counts)}
                                  </Typography>
                                  <Chip size="small" label={basisLabel(m.match_basis)} />
                                  <Chip size="small" variant="outlined" label={`score ${m.score}`} />
                                </Stack>
                              }
                            />
                          </Stack>
                        );
                      })}
                    </RadioGroup>
                  </FormControl>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Code</TableCell>
                          <TableCell>Name</TableCell>
                          <TableCell>Basis</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell>Created</TableCell>
                          <TableCell align="right">FK rows</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {group.members.map((m) => (
                          <TableRow key={m.id} selected={m.id === selectedSurvivor}>
                            <TableCell>{m.customer_code}</TableCell>
                            <TableCell>{m.customer_name}</TableCell>
                            <TableCell>
                              {basisLabel(m.match_basis)} ({m.score})
                            </TableCell>
                            <TableCell>{m.customer_status}</TableCell>
                            <TableCell>{formatDateTime(m.created_at)}</TableCell>
                            <TableCell align="right">{totalRefs(m.reference_counts)}</TableCell>
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
        <DialogTitle>Merge related customers</DialogTitle>
        <DialogContent>
          {mergeGroup ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Anchor <strong>{mergeGroup.anchor_similarity_key}</strong> · {selectedFor(mergeGroup).length} selected ·
                survivor <strong>{survivorForGroup(mergeGroup) ?? '—'}</strong>
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
              {mergeError ? (
                <Alert severity="error" onClose={() => setMergeError(null)}>
                  {mergeError}
                </Alert>
              ) : null}
              {preview ? (
                <Box
                  component="pre"
                  sx={{ fontSize: 12, overflow: 'auto', maxHeight: 280, bgcolor: 'action.hover', p: 1 }}
                  data-testid="related-merge-preview-json"
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
            disabled={!auditNote.trim() || !preview || confirmMutation.isPending || !mergeBody}
            onClick={async () => {
              if (!mergeGroup || !mergeBody) return;
              try {
                setMergeError(null);
                const queued = await confirmMutation.mutateAsync(mergeBody);
                if (queued.task_id) await pollMergeTask(queued.task_id);
                const key = mergeGroup.anchor_similarity_key;
                setMergeGroup(null);
                setPreview(null);
                clearGroupSelection(key);
                void queryClient.invalidateQueries({ queryKey: ['admin-customer-related-groups'] });
              } catch (err) {
                setMergeError(err instanceof Error ? err.message : 'Merge failed');
                void refetch();
              }
            }}
          >
            Confirm merge
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

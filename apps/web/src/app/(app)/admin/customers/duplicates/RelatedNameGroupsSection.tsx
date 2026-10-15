'use client';

import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Radio,
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
import { useState } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ReferenceCount = { label: string; count: number };

type RelatedMember = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  survivor_hint: boolean;
  reference_counts: ReferenceCount[];
  match_basis: 'anchor' | 'contained_prefix' | 'root_similarity';
};

type RelatedGroup = {
  similarity_key: string;
  anchor_similarity_key: string;
  member_count: number;
  members: RelatedMember[];
};

type RelatedGroupsResponse = {
  items: RelatedGroup[];
  total: number;
  customers_scanned: number;
  test_fixture_customers_excluded: number;
};

type MergePreview = {
  loser_ids: number[];
  loser_plans: { customer_id: number; fk_breakdown: ReferenceCount[] }[];
  alias_seal_plan: { alias_seal_minted: unknown[]; alias_seal_conflicts: unknown[] };
};

type Pick = { included: number[]; keeper: number | null };

const BASIS_LABEL: Record<RelatedMember['match_basis'], string> = {
  anchor: 'Shortest name',
  contained_prefix: 'Starts with that name',
  root_similarity: 'Same root name',
};

function totalRefs(counts: ReferenceCount[]): number {
  return counts.reduce((sum, r) => sum + (r.count ?? 0), 0);
}

export function RelatedNameGroupsSection({
  q,
  page,
  pageSize,
  onPageChange,
}: {
  q: string;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  const queryClient = useQueryClient();
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [active, setActive] = useState<RelatedGroup | null>(null);
  const [auditNote, setAuditNote] = useState('');
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [status, setStatus] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);
  const [running, setRunning] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-customer-related-groups', q, page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (q) sp.set('q', q);
      return apiGet<RelatedGroupsResponse>(`/api/v1/customers/duplicate-groups/related?${sp.toString()}`, { signal });
    },
  });

  const pickFor = (g: RelatedGroup): Pick => picks[g.similarity_key] ?? { included: [], keeper: null };
  const setPick = (g: RelatedGroup, next: Pick) => setPicks((prev) => ({ ...prev, [g.similarity_key]: next }));

  const toggle = (g: RelatedGroup, id: number) => {
    const p = pickFor(g);
    const included = p.included.includes(id) ? p.included.filter((x) => x !== id) : [...p.included, id];
    const keeper = p.keeper != null && included.includes(p.keeper) ? p.keeper : null;
    setPick(g, { included, keeper });
  };

  const body = (g: RelatedGroup) => {
    const p = pickFor(g);
    return { similarity_key: g.similarity_key, customer_ids: p.included, survivor_id: p.keeper, audit_note: auditNote.trim() };
  };

  const previewMutation = useMutation({
    mutationFn: (b: Record<string, unknown>) =>
      apiPost<MergePreview>('/api/v1/customers/duplicate-groups/merge-preview', b),
    onSuccess: setPreview,
  });

  const confirm = async (g: RelatedGroup) => {
    setRunning(true);
    try {
      const queued = await apiPost<{ task_id: string }>('/api/v1/customers/duplicate-groups/merge-confirm', body(g));
      for (let i = 0; i < 120; i++) {
        const res = await apiGet<{ state: string; error?: string }>(
          `/api/v1/customers/duplicate-groups/merge-task/${queued.task_id}`
        );
        if (res.state === 'SUCCESS') break;
        if (res.state === 'FAILURE') throw new Error(res.error || 'Merge failed');
        await new Promise((r) => setTimeout(r, 1500));
      }
      setStatus({ severity: 'success', text: 'Merged. The merged names now resolve to the keeper.' });
      setActive(null);
      setPreview(null);
      setPicks((prev) => ({ ...prev, [g.similarity_key]: { included: [], keeper: null } }));
      void queryClient.invalidateQueries({ queryKey: ['admin-customer-related-groups'] });
    } catch (err) {
      setStatus({ severity: 'error', text: err instanceof Error ? err.message : 'Merge failed' });
    } finally {
      setRunning(false);
    }
  };

  const items = data?.items ?? [];
  return (
    <>
      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        Customers whose name starts with another customer&apos;s whole name, or shares its root name. Tick the records
        that are the same business, choose the keeper, then preview. Merged names are added as aliases of the keeper,
        so later files with those names land on the keeper.
      </Alert>
      {status ? (
        <Alert severity={status.severity} sx={{ mb: 2 }} onClose={() => setStatus(null)}>
          {status.text}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          introWhen="always"
          intro={
            <>
              <strong>{data?.total ?? '…'}</strong> related-name group{data?.total === 1 ? '' : 's'} from{' '}
              {data?.customers_scanned ?? '…'} customers. {data?.test_fixture_customers_excluded ?? 0} test-data
              customers are not listed.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && items.length === 0}
          empty={{
            title: 'No related names found',
            description: q ? `No related-name group includes “${q}”.` : 'No customer name starts with another customer’s name.',
          }}
        >
          <Stack spacing={3}>
            {items.map((g) => {
              const p = pickFor(g);
              const ready = p.included.length >= 2 && p.keeper != null;
              return (
                <Paper key={g.similarity_key} variant="outlined" sx={{ p: 2 }} data-testid={`related-group-${g.anchor_similarity_key}`}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                    <Typography variant="subtitle1">{g.members[0]?.customer_name}</Typography>
                    <Chip size="small" label={`${g.member_count} names`} />
                    <Button
                      size="small"
                      variant="contained"
                      disabled={!ready || running}
                      onClick={() => {
                        setActive(g);
                        setAuditNote('');
                        setPreview(null);
                        previewMutation.reset();
                      }}
                    >
                      Merge ticked ({p.included.length})
                    </Button>
                  </Stack>
                  <TableContainer>
                    <Table size="small" aria-label={`Related names for ${g.members[0]?.customer_name ?? ''}`}>
                      <TableHead>
                        <TableRow>
                          <TableCell padding="checkbox">Same business</TableCell>
                          <TableCell padding="checkbox">Keeper</TableCell>
                          <TableCell>Customer</TableCell>
                          <TableCell>Code</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell>Why listed</TableCell>
                          <TableCell align="right">Rows</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {g.members.map((m) => {
                          const included = p.included.includes(m.id);
                          return (
                            <TableRow key={m.id} selected={p.keeper === m.id}>
                              <TableCell padding="checkbox">
                                <Checkbox
                                  checked={included}
                                  onChange={() => toggle(g, m.id)}
                                  inputProps={{ 'aria-label': `Include ${m.customer_name}` }}
                                />
                              </TableCell>
                              <TableCell padding="checkbox">
                                <Radio
                                  checked={p.keeper === m.id}
                                  disabled={!included}
                                  onChange={() => setPick(g, { ...p, keeper: m.id })}
                                  inputProps={{ 'aria-label': `Keep ${m.customer_name}` }}
                                />
                              </TableCell>
                              <TableCell>
                                {m.customer_name}
                                {m.survivor_hint ? ' (suggested keeper)' : ''}
                              </TableCell>
                              <TableCell>{m.customer_code}</TableCell>
                              <TableCell>{m.customer_status}</TableCell>
                              <TableCell>{BASIS_LABEL[m.match_basis] ?? m.match_basis}</TableCell>
                              <TableCell align="right">{totalRefs(m.reference_counts)}</TableCell>
                            </TableRow>
                          );
                        })}
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
              Page {page} / {Math.max(1, Math.ceil((data?.total ?? 0) / pageSize))}
            </Typography>
            <Button disabled={page * pageSize >= (data?.total ?? 0)} onClick={() => onPageChange(page + 1)}>
              Next
            </Button>
          </Stack>
        </ModuleDataSection>
      </Paper>

      <Dialog open={active !== null} onClose={() => !running && setActive(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Merge related names</DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Keep <strong>{active.members.find((m) => m.id === pickFor(active).keeper)?.customer_name}</strong> and merge{' '}
                {pickFor(active).included.length - 1} other record{pickFor(active).included.length === 2 ? '' : 's'} into it.
              </Typography>
              <TextField
                label="Reason (required)"
                value={auditNote}
                onChange={(e) => {
                  setAuditNote(e.target.value);
                  setPreview(null);
                }}
                multiline
                minRows={2}
                required
                fullWidth
                disabled={running}
              />
              {previewMutation.isError ? (
                <Alert severity="error">{toQueryError(previewMutation.error)?.message ?? 'Preview failed'}</Alert>
              ) : null}
              {preview ? (
                <Typography variant="body2" component="ul" sx={{ m: 0, pl: 2.5 }} data-testid="related-merge-plan">
                  <li>
                    {preview.loser_plans.reduce((n, lp) => n + totalRefs(lp.fk_breakdown), 0)} rows move to the keeper.
                  </li>
                  <li>
                    {preview.alias_seal_plan.alias_seal_minted.length} alias
                    {preview.alias_seal_plan.alias_seal_minted.length === 1 ? '' : 'es'} added for the merged names
                    {preview.alias_seal_plan.alias_seal_conflicts.length > 0
                      ? `; ${preview.alias_seal_plan.alias_seal_conflicts.length} already belong to another customer and stay as they are`
                      : ''}
                    .
                  </li>
                </Typography>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button disabled={running} onClick={() => setActive(null)}>
            Cancel
          </Button>
          <Button
            disabled={!auditNote.trim() || previewMutation.isPending || running || !active}
            onClick={() => active && previewMutation.mutate(body(active))}
          >
            Preview
          </Button>
          <Button variant="contained" disabled={!preview || running || !active} onClick={() => active && void confirm(active)}>
            {running ? 'Merging…' : 'Confirm merge'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

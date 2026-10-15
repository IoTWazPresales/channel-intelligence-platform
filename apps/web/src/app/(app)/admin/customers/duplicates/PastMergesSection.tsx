'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
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
import { useState, type ReactNode } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ReferenceCount = { label: string; count: number };

export type MergeRecord = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  created_at: string | null;
  origin: string | null;
  merged_into_customer_id: number | null;
  merged_at: string | null;
  reference_rows: number;
  reference_counts: ReferenceCount[];
  sellthrough_rows: number;
  sellthrough_units: number;
  cases: number;
  alias_count: number;
  aliases: string[];
};

type PastMerge = { keeper: MergeRecord; merged: MergeRecord[] };

type PastMergesResponse = {
  items: PastMerge[];
  page: number;
  page_size: number;
  total: number;
  test_fixture_merges_excluded: number;
  note: string;
};

type KeeperPlan = {
  current_keeper: { id: number; code: string; name: string; status: string };
  new_keeper: { id: number; code: string; name: string; status: string };
  new_keeper_status_after: string;
  rows_to_move: number;
  rows_to_move_by_table: Record<string, number>;
  rows_already_on_new_keeper: number;
  other_merged_records_redirected: number[];
  alias_seal_plan: {
    alias_seal_minted: { normalized_token: string }[];
    alias_seal_conflicts: { normalized_token: string; existing_customer_id: number | null }[];
  };
  kept: string;
};

type Choice = { keeper: MergeRecord; candidate: MergeRecord };

const fmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

function EvidenceRow({ record, role, action }: { record: MergeRecord; role: string; action?: ReactNode }) {
  return (
    <TableRow data-testid={`past-merge-record-${record.id}`}>
      <TableCell>
        <Stack spacing={0.5}>
          <Typography variant="body2" fontWeight={600}>
            {record.customer_name}
          </Typography>
          <Chip size="small" label={role} color={role === 'Keeper' ? 'primary' : 'default'} sx={{ width: 'fit-content' }} />
        </Stack>
      </TableCell>
      <TableCell>{record.customer_code}</TableCell>
      <TableCell>
        <Typography variant="body2">{record.origin ?? '—'}</Typography>
        <Typography variant="caption" color="text.secondary">
          Created {formatDate(record.created_at)}
          {record.merged_at ? ` · merged ${formatDate(record.merged_at)}` : ''}
        </Typography>
      </TableCell>
      <TableCell align="right">{fmt.format(record.reference_rows)}</TableCell>
      <TableCell align="right">
        {fmt.format(record.sellthrough_rows)} rows · {fmt.format(record.sellthrough_units)} units
      </TableCell>
      <TableCell align="right">{fmt.format(record.cases)}</TableCell>
      <TableCell>
        {record.alias_count === 0 ? (
          '—'
        ) : (
          <Typography variant="body2">
            {record.alias_count}: {record.aliases.join(', ')}
            {record.alias_count > record.aliases.length ? ', …' : ''}
          </Typography>
        )}
      </TableCell>
      <TableCell>{action ?? null}</TableCell>
    </TableRow>
  );
}

export function PastMergesSection({
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
  const [choice, setChoice] = useState<Choice | null>(null);
  const [auditNote, setAuditNote] = useState('');
  const [plan, setPlan] = useState<KeeperPlan | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-customer-merge-history', q, page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (q) sp.set('q', q);
      return apiGet<PastMergesResponse>(`/api/v1/customers/merge-history?${sp.toString()}`, { signal });
    },
  });

  const body = choice
    ? { current_keeper_id: choice.keeper.id, new_keeper_id: choice.candidate.id, audit_note: auditNote.trim() }
    : null;

  const previewMutation = useMutation({
    mutationFn: (b: Record<string, unknown>) =>
      apiPost<KeeperPlan>('/api/v1/customers/merge-history/change-keeper-preview', b),
    onSuccess: setPlan,
  });
  const confirmMutation = useMutation({
    mutationFn: (b: Record<string, unknown>) =>
      apiPost<{ rows_moved: number }>('/api/v1/customers/merge-history/change-keeper-confirm', b),
    onSuccess: (res) => {
      setDone(
        `${choice?.candidate.customer_name} is now the keeper. ${fmt.format(res.rows_moved)} rows moved from ${choice?.keeper.customer_name}.`
      );
      setChoice(null);
      setPlan(null);
      void queryClient.invalidateQueries({ queryKey: ['admin-customer-merge-history'] });
    },
  });

  const open = (keeper: MergeRecord, candidate: MergeRecord) => {
    setChoice({ keeper, candidate });
    setAuditNote('');
    setPlan(null);
    previewMutation.reset();
    confirmMutation.reset();
  };

  const items = data?.items ?? [];
  return (
    <>
      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        Each merge kept one record (the keeper) and pointed the others at it. All rows now sit on the keeper;
        which rows came from which record before the merge was not recorded. To keep a different record, use{' '}
        <strong>Make this the keeper</strong>: you see what moves before anything changes.
      </Alert>
      {done ? (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setDone(null)}>
          {done}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          introWhen="always"
          intro={
            <>
              <strong>{data?.total ?? '…'}</strong> keeper{data?.total === 1 ? '' : 's'} with merged records
              {q ? (
                <>
                  {' '}
                  matching <strong>{q}</strong>
                </>
              ) : null}
              . {data?.test_fixture_merges_excluded ?? 0} test-data merges are not listed.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && items.length === 0}
          empty={{
            title: 'No past merges found',
            description: q ? `No merged customer matches “${q}”.` : 'No customer has been merged yet.',
          }}
        >
          <Stack spacing={3}>
            {items.map((group) => (
              <Paper key={group.keeper.id} variant="outlined" sx={{ p: 2 }} data-testid={`past-merge-${group.keeper.id}`}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>
                  {group.keeper.customer_name}
                </Typography>
                <TableContainer>
                  <Table size="small" aria-label={`Records merged into ${group.keeper.customer_name}`}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Customer</TableCell>
                        <TableCell>Code</TableCell>
                        <TableCell>Origin</TableCell>
                        <TableCell align="right">Rows now</TableCell>
                        <TableCell align="right">Sell-through</TableCell>
                        <TableCell align="right">Cases</TableCell>
                        <TableCell>Aliases</TableCell>
                        <TableCell />
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      <EvidenceRow record={group.keeper} role="Keeper" />
                      {group.merged.map((m) => (
                        <EvidenceRow
                          key={m.id}
                          record={m}
                          role="Merged"
                          action={
                            <Button size="small" variant="outlined" onClick={() => open(group.keeper, m)}>
                              Make this the keeper
                            </Button>
                          }
                        />
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            ))}
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

      <Dialog open={choice !== null} onClose={() => setChoice(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Change the keeper</DialogTitle>
        <DialogContent>
          {choice ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Keep <strong>{choice.candidate.customer_name}</strong> ({choice.candidate.customer_code}) and merge{' '}
                <strong>{choice.keeper.customer_name}</strong> ({choice.keeper.customer_code}) into it.
              </Typography>
              <TextField
                label="Reason (required)"
                value={auditNote}
                onChange={(e) => {
                  setAuditNote(e.target.value);
                  setPlan(null);
                }}
                multiline
                minRows={2}
                required
                fullWidth
              />
              {previewMutation.isError ? <Alert severity="error">{toQueryError(previewMutation.error)?.message ?? 'Preview failed'}</Alert> : null}
              {confirmMutation.isError ? <Alert severity="error">{toQueryError(confirmMutation.error)?.message ?? 'Keeper change failed'}</Alert> : null}
              {plan ? (
                <Box data-testid="keeper-change-plan">
                  <Typography variant="body2" component="ul" sx={{ m: 0, pl: 2.5 }}>
                    <li>
                      {fmt.format(plan.rows_to_move)} rows move from {plan.current_keeper.name} to {plan.new_keeper.name}.
                    </li>
                    <li>{plan.kept}</li>
                    <li>
                      {plan.new_keeper.name} becomes {plan.new_keeper_status_after}.
                    </li>
                    {plan.other_merged_records_redirected.length > 0 ? (
                      <li>{plan.other_merged_records_redirected.length} other merged records now point at the new keeper.</li>
                    ) : null}
                    <li>
                      {plan.alias_seal_plan.alias_seal_minted.length} alias
                      {plan.alias_seal_plan.alias_seal_minted.length === 1 ? '' : 'es'} added so the old name finds the
                      new keeper
                      {plan.alias_seal_plan.alias_seal_conflicts.length > 0
                        ? `; ${plan.alias_seal_plan.alias_seal_conflicts.length} already belong to another customer and stay as they are`
                        : ''}
                      .
                    </li>
                  </Typography>
                </Box>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChoice(null)}>Cancel</Button>
          <Button disabled={!auditNote.trim() || previewMutation.isPending || !body} onClick={() => body && previewMutation.mutate(body)}>
            Preview
          </Button>
          <Button
            variant="contained"
            disabled={!plan || confirmMutation.isPending || !body}
            onClick={() => body && confirmMutation.mutate(body)}
          >
            Confirm keeper change
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

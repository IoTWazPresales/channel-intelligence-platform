/**
 * Distributor attribution review — proposed / conflict lines (Unit 6f / D-040).
 */
'use client';

import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';

type ReviewItem = {
  line_id: number;
  case_id: number;
  period_label: string | null;
  customer_token: string | null;
  norm_token: string;
  customer_id: number | null;
  distributor_id: number | null;
  distributor_label: string | null;
  distributor_attribution_status: string;
  product_id: number | null;
  quantity_units: number | null;
};

type ReviewResponse = {
  items: ReviewItem[];
  total: number;
  status_counts: Record<string, number>;
};

export const DISTRIBUTOR_ATTRIBUTION_SECTION_ID = 'distributor-attribution-review-section';

export function DistributorAttributionReviewSection() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<'token_proposed,conflict' | 'conflict' | 'token_proposed'>(
    'token_proposed,conflict',
  );
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [overrideDistId, setOverrideDistId] = useState('');
  const [reason, setReason] = useState('steward distributor attribution');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reviewQ = useQuery({
    queryKey: ['distributor-attribution-review', statusFilter],
    queryFn: ({ signal }) =>
      apiGet<ReviewResponse>(
        `/api/v1/commercial-planner/lineup/distributor-attribution/review?limit=200&status=${encodeURIComponent(statusFilter)}`,
        { signal },
      ),
  });

  const items = reviewQ.data?.items ?? [];
  const counts = reviewQ.data?.status_counts ?? {};

  const softClearMut = useMutation({
    mutationFn: (vars: { line_ids: number[]; reason: string }) =>
      apiPost<{ cleared_count: number }>(
        '/api/v1/commercial-planner/lineup/distributor-attribution/soft-clear',
        vars,
      ),
    onSuccess: (data) => {
      setMsg(`Soft-cleared distributor on ${data.cleared_count} line(s)`);
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ['distributor-attribution-review'] });
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'Soft-clear failed'),
  });

  const overrideMut = useMutation({
    mutationFn: (vars: { line_ids: number[]; distributor_id: number; reason: string }) =>
      apiPost<{ updated_count: number }>(
        '/api/v1/commercial-planner/lineup/distributor-attribution/override',
        vars,
      ),
    onSuccess: (data) => {
      setMsg(`Override set on ${data.updated_count} line(s)`);
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ['distributor-attribution-review'] });
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'Override failed'),
  });

  const confirmerMut = useMutation({
    mutationFn: () =>
      apiPost<{ updated_count: number; action_counts: Record<string, number> }>(
        '/api/v1/commercial-planner/lineup/distributor-attribution/confirmer/apply',
        {},
      ),
    onSuccess: (data) => {
      setMsg(`Confirmer updated ${data.updated_count} line(s)`);
      void qc.invalidateQueries({ queryKey: ['distributor-attribution-review'] });
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'Confirmer failed'),
  });

  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  return (
    <Card variant="outlined" id={DISTRIBUTOR_ATTRIBUTION_SECTION_ID} data-testid="distributor-attribution-review">
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="h6">Distributor attribution review</Typography>
          <Typography variant="body2" color="text.secondary">
            Token proposes; shipment confirms. Soft-clear removes distributor only (keeps Open Channel).
          </Typography>
          {err ? (
            <Alert severity="error" onClose={() => setErr(null)}>
              {err}
            </Alert>
          ) : null}
          {msg ? (
            <Alert severity="success" onClose={() => setMsg(null)}>
              {msg}
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip
              label={`All ${counts.all ?? items.length}`}
              color={statusFilter === 'token_proposed,conflict' ? 'primary' : 'default'}
              onClick={() => setStatusFilter('token_proposed,conflict')}
              data-testid="dist-attr-filter-all"
            />
            <Chip
              label={`Proposed ${counts.token_proposed ?? 0}`}
              color={statusFilter === 'token_proposed' ? 'primary' : 'default'}
              onClick={() => setStatusFilter('token_proposed')}
              data-testid="dist-attr-filter-proposed"
            />
            <Chip
              label={`Conflict ${counts.conflict ?? 0}`}
              color={statusFilter === 'conflict' ? 'warning' : 'default'}
              onClick={() => setStatusFilter('conflict')}
              data-testid="dist-attr-filter-conflict"
            />
            <Button
              size="small"
              variant="outlined"
              data-testid="dist-attr-run-confirmer"
              disabled={confirmerMut.isPending}
              onClick={() => confirmerMut.mutate()}
            >
              Run shipment confirmer
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              label="Override distributor id"
              value={overrideDistId}
              onChange={(e) => setOverrideDistId(e.target.value)}
              inputProps={{ 'data-testid': 'dist-attr-override-id' }}
            />
            <TextField
              size="small"
              label="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              inputProps={{ 'data-testid': 'dist-attr-reason' }}
            />
            <Button
              size="small"
              variant="contained"
              disabled={!selectedIds.length || overrideMut.isPending}
              data-testid="dist-attr-override"
              onClick={() => {
                const id = Number(overrideDistId);
                if (!Number.isFinite(id) || id < 1) {
                  setErr('Override distributor id required');
                  return;
                }
                overrideMut.mutate({ line_ids: selectedIds, distributor_id: id, reason });
              }}
            >
              Override selected
            </Button>
            <Button
              size="small"
              color="warning"
              variant="outlined"
              disabled={!selectedIds.length || softClearMut.isPending}
              data-testid="dist-attr-soft-clear"
              onClick={() => softClearMut.mutate({ line_ids: selectedIds, reason })}
            >
              Soft-clear dist
            </Button>
          </Stack>
          {reviewQ.isLoading ? (
            <Typography variant="body2">Loading…</Typography>
          ) : !items.length ? (
            <Alert severity="info" data-testid="dist-attr-empty">
              No lines in selected attribution statuses.
            </Alert>
          ) : (
            <Stack spacing={0.5} data-testid="dist-attr-list">
              {items.map((it) => {
                const on = selected.has(it.line_id);
                return (
                  <Stack
                    key={it.line_id}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ cursor: 'pointer' }}
                    onClick={() => {
                      setSelected((prev) => {
                        const n = new Set(prev);
                        if (n.has(it.line_id)) n.delete(it.line_id);
                        else n.add(it.line_id);
                        return n;
                      });
                    }}
                    data-testid={`dist-attr-row-${it.line_id}`}
                  >
                    <Chip size="small" label={on ? '✓' : '○'} />
                    <Chip
                      size="small"
                      color={it.distributor_attribution_status === 'conflict' ? 'warning' : 'default'}
                      label={it.distributor_attribution_status}
                    />
                    <Typography variant="body2">
                      line {it.line_id} · case {it.case_id} · {it.customer_token} → dist{' '}
                      {it.distributor_label ?? it.distributor_id ?? '—'}
                    </Typography>
                  </Stack>
                );
              })}
            </Stack>
          )}
          <Box />
        </Stack>
      </CardContent>
    </Card>
  );
}

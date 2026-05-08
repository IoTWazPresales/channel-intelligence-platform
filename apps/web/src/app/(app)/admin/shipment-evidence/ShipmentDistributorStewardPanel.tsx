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
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

export type ShipmentDistTokenRow = {
  import_job_id: number;
  party: 'bill_to' | 'ship_to';
  normalized_token: string;
  representative_raw_token: string;
  row_count: number;
  total_quantity: number | null;
  total_amount: number | null;
  sample_line_ids: number[];
  sample_source_row_numbers: number[];
  import_job_file_name: string | null;
};

type DistributorHit = { id: number; distributor_code: string; distributor_name: string };

function partyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : 'Ship To';
}

export function ShipmentDistributorStewardPanel({ importJobId }: { importJobId: number | null }) {
  const qc = useQueryClient();
  const [mapOpen, setMapOpen] = useState(false);
  const [provOpen, setProvOpen] = useState(false);
  const [active, setActive] = useState<ShipmentDistTokenRow | null>(null);
  const [distQ, setDistQ] = useState('');
  const [pickDistId, setPickDistId] = useState<number | ''>('');
  const [provName, setProvName] = useState('');
  const [provCode, setProvCode] = useState('');
  const [provConfirmSuspicious, setProvConfirmSuspicious] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, refetch, isLoading } = useQuery({
    queryKey: ['shipment-evidence-dist-tokens', importJobId],
    queryFn: ({ signal }) => {
      const q = importJobId != null ? `?import_job_id=${importJobId}` : '';
      return apiGet<{ items: ShipmentDistTokenRow[] }>(
        `/api/v1/shipment-evidence/distributor-stewardship/tokens${q}`,
        { signal }
      );
    },
  });

  const rows = data?.items ?? [];

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search-shipment-steward', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorHit[] }>(
        `/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=20`,
        { signal }
      ),
    enabled: distQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const jobIdsForReprocess = useMemo(() => [...new Set(rows.map((r) => r.import_job_id))].sort((a, b) => b - a), [rows]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['shipment-evidence-dist-tokens'] });
    void qc.invalidateQueries({ queryKey: ['shipment-evidence'] });
  };

  const mapMut = useMutation({
    mutationFn: (body: { import_job_id: number; party: string; raw_token: string; distributor_id: number }) =>
      apiPost<Record<string, unknown>>('/api/v1/shipment-evidence/distributor-stewardship/map-to-distributor', body),
    onSuccess: () => {
      setActionError(null);
      setMapOpen(false);
      setActive(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const provMut = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<Record<string, unknown>>(
        '/api/v1/shipment-evidence/distributor-stewardship/create-provisional-distributor',
        body
      ),
    onSuccess: () => {
      setActionError(null);
      setProvOpen(false);
      setActive(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const reprocessMut = useMutation({
    mutationFn: (jobId: number) =>
      apiPost<Record<string, unknown>>('/api/v1/shipment-evidence/distributor-stewardship/reprocess-resolution', {
        import_job_id: jobId,
      }),
    onSuccess: () => {
      setActionError(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const openMap = (r: ShipmentDistTokenRow) => {
    setActive(r);
    setPickDistId('');
    setDistQ('');
    setActionError(null);
    setMapOpen(true);
  };

  const openProv = (r: ShipmentDistTokenRow) => {
    setActive(r);
    setProvName(r.representative_raw_token.slice(0, 200));
    setProvCode('');
    setProvConfirmSuspicious(false);
    setActionError(null);
    setProvOpen(true);
  };

  return (
    <Paper sx={{ p: 2 }} data-testid="shipment-distributor-steward-panel">
      <Stack spacing={2}>
        <Typography variant="h6">Distributor stewardship (Bill To / Ship To)</Typography>
        <Typography variant="body2" color="text.secondary">
          Unresolved Bill To / Ship To tokens from shipment evidence imports. Mapping creates an approved distributor
          source-token alias for the import job&apos;s source (same table as DSI). Bill To is primary resolution
          evidence; Ship To is secondary. Re-run resolution refreshes distributor_id and status on affected lines.
        </Typography>
        {importJobId == null ? (
          <Alert severity="info">
            Showing unresolved tokens across all jobs. Use the Import job ID filter above to focus one job.
          </Alert>
        ) : null}
        {actionError ? (
          <Alert severity="error" onClose={() => setActionError(null)}>
            {actionError}
          </Alert>
        ) : null}
        {isLoading ? (
          <Typography variant="body2">Loading…</Typography>
        ) : rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No unresolved distributor tokens in the current scope.
          </Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Job</TableCell>
                <TableCell>Party</TableCell>
                <TableCell>Token (sample)</TableCell>
                <TableCell align="right">Rows</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Amount</TableCell>
                <TableCell>Sample rows</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={`${r.import_job_id}-${r.party}-${r.normalized_token}`}>
                  <TableCell>
                    <Typography variant="body2">{r.import_job_id}</Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {r.import_job_file_name ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={partyLabel(r.party)} color={r.party === 'bill_to' ? 'primary' : 'default'} />
                  </TableCell>
                  <TableCell sx={{ maxWidth: 280 }}>
                    <Typography variant="body2" noWrap title={r.representative_raw_token}>
                      {r.representative_raw_token}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{r.row_count}</TableCell>
                  <TableCell align="right">{r.total_quantity ?? '—'}</TableCell>
                  <TableCell align="right">{r.total_amount ?? '—'}</TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {(r.sample_source_row_numbers ?? []).slice(0, 6).join(', ')}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Button size="small" variant="outlined" onClick={() => openMap(r)}>
                        Map…
                      </Button>
                      <Button size="small" variant="outlined" onClick={() => openProv(r)}>
                        Provisional…
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {jobIdsForReprocess.length > 0 ? (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Re-run strict distributor resolution
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {jobIdsForReprocess.map((jid) => (
                <Button
                  key={jid}
                  size="small"
                  variant="text"
                  disabled={reprocessMut.isPending}
                  onClick={() => reprocessMut.mutate(jid)}
                >
                  Job {jid}
                </Button>
              ))}
            </Stack>
          </Box>
        ) : null}
      </Stack>

      <Dialog open={mapOpen} onClose={() => setMapOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Map token to distributor</DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Job {active.import_job_id} · {partyLabel(active.party)} ·{' '}
                <strong>{active.representative_raw_token}</strong>
              </Typography>
              <TextField
                label="Search distributors"
                size="small"
                value={distQ}
                onChange={(e) => setDistQ(e.target.value)}
                fullWidth
              />
              <TextField
                select
                label="Distributor"
                size="small"
                value={pickDistId}
                onChange={(e) => setPickDistId(e.target.value === '' ? '' : Number(e.target.value))}
                fullWidth
              >
                <MenuItem value="">
                  <em>Select…</em>
                </MenuItem>
                {distHits.map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.distributor_code} — {d.distributor_name}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!active || pickDistId === '' || mapMut.isPending}
            onClick={() => {
              if (!active || pickDistId === '') return;
              mapMut.mutate({
                import_job_id: active.import_job_id,
                party: active.party,
                raw_token: active.representative_raw_token,
                distributor_id: Number(pickDistId),
              });
            }}
          >
            Map &amp; reprocess
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={provOpen} onClose={() => setProvOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create provisional distributor</DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Job {active.import_job_id} · {partyLabel(active.party)} ·{' '}
                <strong>{active.representative_raw_token}</strong>
              </Typography>
              <TextField
                label="Display name"
                size="small"
                value={provName}
                onChange={(e) => setProvName(e.target.value)}
                fullWidth
              />
              <TextField
                label="Distributor code (optional)"
                size="small"
                value={provCode}
                onChange={(e) => setProvCode(e.target.value)}
                helperText="Leave blank to auto-generate a TMP-DIST-… code."
                fullWidth
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={provConfirmSuspicious}
                    onChange={(e) => setProvConfirmSuspicious(e.target.checked)}
                  />
                }
                label="Confirm if token looks like a placeholder (required for suspicious tokens)"
              />
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProvOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!active || provMut.isPending}
            onClick={() => {
              if (!active) return;
              provMut.mutate({
                import_job_id: active.import_job_id,
                party: active.party,
                raw_token: active.representative_raw_token,
                display_name: provName.trim() || null,
                distributor_code: provCode.trim() || null,
                confirm_for_suspicious_token: provConfirmSuspicious,
              });
            }}
          >
            Create &amp; reprocess
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

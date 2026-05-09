'use client';

import {
  Alert,
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

export type ShipmentMappingCandidateRow = {
  id: number;
  import_job_id: number;
  entity_type: string;
  normalized_key: string;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  suggested_distributor_code: string | null;
  suggested_distributor_name: string | null;
  suggested_action: string | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
};

type DistributorHit = { id: number; distributor_code: string; distributor_name: string };

const TERMINAL = new Set(['resolved', 'ignored', 'waived_open_channel']);

function partyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : party === 'ship_to' ? 'Ship To' : party;
}

function sampleToken(r: ShipmentMappingCandidateRow): string {
  const s = r.sample_raw_values;
  if (Array.isArray(s) && s.length > 0 && typeof s[0] === 'string' && s[0].trim()) {
    return s[0].trim();
  }
  return (r.normalized_key || '').trim() || '—';
}

function contextParty(ctx: Record<string, unknown> | null): string {
  if (!ctx || typeof ctx.party !== 'string') return '—';
  return partyLabel(ctx.party);
}

export function ShipmentDistributorStewardPanel({ importJobId }: { importJobId: number | null }) {
  const qc = useQueryClient();
  const [mapOpen, setMapOpen] = useState(false);
  const [provOpen, setProvOpen] = useState(false);
  const [active, setActive] = useState<ShipmentMappingCandidateRow | null>(null);
  const [distQ, setDistQ] = useState('');
  const [pickDistId, setPickDistId] = useState<number | ''>('');
  const [provName, setProvName] = useState('');
  const [provCode, setProvCode] = useState('');
  const [provConfirmSuspicious, setProvConfirmSuspicious] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const candidatesUrl =
    importJobId != null
      ? `/api/v1/shipment-evidence/import-jobs/${importJobId}/mapping-candidates`
      : '';

  const { data: rawRows, refetch, isLoading } = useQuery({
    queryKey: ['shipment-evidence-mapping-candidates', importJobId],
    queryFn: ({ signal }) => apiGet<ShipmentMappingCandidateRow[]>(candidatesUrl, { signal }),
    enabled: importJobId != null,
  });

  const rows = useMemo(
    () => (rawRows ?? []).filter((r) => !TERMINAL.has((r.status || '').trim())),
    [rawRows]
  );

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

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['shipment-evidence'] });
    if (importJobId != null) {
      void qc.invalidateQueries({ queryKey: ['shipment-evidence-mapping-candidates', importJobId] });
    }
  };

  const mapMut = useMutation({
    mutationFn: (body: { candidate_id: number; distributor_id: number; raw_token: string | null }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/map-distributor`,
        { distributor_id: body.distributor_id, raw_token: body.raw_token }
      ),
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
    mutationFn: (body: {
      candidate_id: number;
      display_name: string | null;
      distributor_code: string | null;
      confirm_for_suspicious_token: boolean;
    }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/create-provisional-distributor`,
        {
          display_name: body.display_name,
          distributor_code: body.distributor_code,
          confirm_for_suspicious_token: body.confirm_for_suspicious_token,
        }
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

  const openMap = (r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setPickDistId('');
    setDistQ('');
    setActionError(null);
    setMapOpen(true);
  };

  const openProv = (r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setProvName(sampleToken(r).slice(0, 200));
    setProvCode('');
    setProvConfirmSuspicious(false);
    setActionError(null);
    setProvOpen(true);
  };

  const actionChipColor = (a: string | null) => {
    switch (a) {
      case 'map_distributor':
        return 'success' as const;
      case 'create_provisional_distributor':
        return 'warning' as const;
      case 'needs_review':
        return 'error' as const;
      default:
        return 'default' as const;
    }
  };

  return (
    <Paper sx={{ p: 2 }} data-testid="shipment-distributor-steward-panel">
      <Stack spacing={2}>
        <Typography variant="h6">Distributor mapping candidates (import job)</Typography>
        <Typography variant="body2" color="text.secondary">
          One row per unresolved Bill To / Ship To token (Bill To preferred when present). Suggested actions are
          hints only; map and provisional apply strictly (approved alias + line updates).
        </Typography>
        {importJobId == null ? (
          <Alert severity="info">
            Set <strong>Import job ID</strong> in the filters above to load candidates for that job.
          </Alert>
        ) : null}
        {actionError ? (
          <Alert severity="error" onClose={() => setActionError(null)}>
            {actionError}
          </Alert>
        ) : null}
        {importJobId != null && isLoading ? (
          <Typography variant="body2">Loading…</Typography>
        ) : importJobId != null && rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No open distributor mapping candidates for this job (all resolved or none unresolved).
          </Typography>
        ) : importJobId != null ? (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Party</TableCell>
                <TableCell>Token (sample)</TableCell>
                <TableCell align="right">Rows</TableCell>
                <TableCell align="right">Qty / value</TableCell>
                <TableCell>Suggested</TableCell>
                <TableCell>Match</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Typography variant="body2">{contextParty(r.context)}</Typography>
                  </TableCell>
                  <TableCell sx={{ maxWidth: 260 }}>
                    <Typography variant="body2" noWrap title={sampleToken(r)}>
                      {sampleToken(r)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" noWrap title={r.normalized_key}>
                      key: {r.normalized_key}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{r.row_count}</TableCell>
                  <TableCell align="right">
                    <Typography variant="caption" display="block">
                      {r.total_units ?? '—'} / {r.total_reported_value ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5} alignItems="flex-start">
                      {r.suggested_action ? (
                        <Chip size="small" label={r.suggested_action} color={actionChipColor(r.suggested_action)} />
                      ) : null}
                      {r.suggested_distributor_code || r.suggested_distributor_name ? (
                        <Typography variant="caption" color="text.secondary">
                          {(r.suggested_distributor_code || '').trim()}
                          {r.suggested_distributor_name ? ` — ${r.suggested_distributor_name}` : ''}
                        </Typography>
                      ) : null}
                      {r.confidence_score != null ? (
                        <Typography variant="caption" color="text.secondary">
                          score {r.confidence_score.toFixed(2)}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ maxWidth: 200 }}>
                    <Typography variant="caption" color="text.secondary">
                      {r.match_reason ?? '—'}
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
        ) : null}
      </Stack>

      <Dialog open={mapOpen} onClose={() => setMapOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Map token to distributor</DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Candidate {active.id} · {contextParty(active.context)} · <strong>{sampleToken(active)}</strong>
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
                candidate_id: active.id,
                distributor_id: Number(pickDistId),
                raw_token: sampleToken(active) !== '—' ? sampleToken(active) : null,
              });
            }}
          >
            Map
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={provOpen} onClose={() => setProvOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create provisional distributor</DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Candidate {active.id} · {contextParty(active.context)} · <strong>{sampleToken(active)}</strong>
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
                candidate_id: active.id,
                display_name: provName.trim() || null,
                distributor_code: provCode.trim() || null,
                confirm_for_suspicious_token: provConfirmSuspicious,
              });
            }}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────

type CommercialLineupCase = {
  id: number;
  import_job_id: number | null;
  commercial_plan_id: number | null;
  file_name: string | null;
  period_label: string | null;
  country_code: string | null;
  currency_code: string | null;
  commercial_status: string;
  notes: string | null;
  accepted_at: string | null;
  accepted_by: string | null;
  line_count: number;
  created_at: string | null;
};

type CommercialLineupLine = {
  id: number;
  case_id: number;
  source_row_number: number | null;
  product_sku: string | null;
  product_name: string | null;
  product_part_number: string | null;
  product_sales_model_name: string | null;
  sku_raw: string | null;
  part_number_raw: string | null;
  model_raw: string | null;
  quantity_units: number | null;
  msrp_local: number | null;
  promo_price_evidence_local: number | null;
  dap_evidence_local: number | null;
  row_status: string;
  dap_semantics_note?: string;
};

type CaseLinesResponse = {
  lines: CommercialLineupLine[];
  dap_semantics_note: string;
};

// ── Status chip colors ─────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> =
  {
    draft_imported: 'default',
    validated: 'info',
    pending_review: 'warning',
    accepted: 'success',
    po_pending: 'secondary',
    po_issued: 'secondary',
    in_fulfillment: 'info',
    received_closed: 'default',
    cancelled: 'error',
  };

const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  draft_imported: ['validated', 'cancelled'],
  validated: ['pending_review', 'cancelled'],
  pending_review: ['accepted', 'validated', 'cancelled'],
  accepted: ['po_pending', 'cancelled'],
  po_pending: ['po_issued', 'cancelled'],
  po_issued: ['in_fulfillment'],
  in_fulfillment: ['received_closed'],
  received_closed: [],
  cancelled: [],
};

// ── Sub-components ────────────────────────────────────────────────────────────

function CaseLinesDialog({
  open,
  onClose,
  caseId,
  caseLabel,
}: {
  open: boolean;
  onClose: () => void;
  caseId: number;
  caseLabel: string;
}) {
  const { data, isLoading } = useQuery<CaseLinesResponse>({
    queryKey: ['commercial-lineup-case-lines', caseId],
    queryFn: ({ signal }) =>
      apiGet<CaseLinesResponse>(`/api/v1/commercial-planner/lineup-cases/${caseId}/lines`, { signal }),
    enabled: open,
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" aria-labelledby="case-lines-title">
      <DialogTitle id="case-lines-title">Lines — {caseLabel}</DialogTitle>
      <DialogContent dividers>
        {data?.dap_semantics_note && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {data.dap_semantics_note}
          </Alert>
        )}
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        ) : !data?.lines?.length ? (
          <Typography color="text.secondary">No lines in this case.</Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>SKU (raw / resolved)</TableCell>
                  <TableCell>Part #</TableCell>
                  <TableCell>Model</TableCell>
                  <TableCell>Units</TableCell>
                  <TableCell>MSRP local</TableCell>
                  <TableCell>Promo evidence</TableCell>
                  <TableCell>DAP evidence</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.lines.map((ln) => (
                  <TableRow key={ln.id}>
                    <TableCell>{ln.source_row_number ?? ln.id}</TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {ln.product_sku ?? ln.sku_raw ?? '—'}
                      </Typography>
                      {ln.product_sku && ln.sku_raw && ln.product_sku !== ln.sku_raw && (
                        <Typography variant="caption" color="text.secondary">
                          raw: {ln.sku_raw}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{ln.product_part_number ?? ln.part_number_raw ?? '—'}</TableCell>
                    <TableCell>{ln.product_sales_model_name ?? ln.model_raw ?? '—'}</TableCell>
                    <TableCell>{ln.quantity_units != null ? ln.quantity_units.toLocaleString() : '—'}</TableCell>
                    <TableCell>{ln.msrp_local != null ? ln.msrp_local.toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      {ln.promo_price_evidence_local != null ? ln.promo_price_evidence_local.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell>
                      {ln.dap_evidence_local != null ? ln.dap_evidence_local.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell>
                      <Chip label={ln.row_status} size="small" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function StatusTransitionDialog({
  open,
  onClose,
  currentCase,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  currentCase: CommercialLineupCase;
  onConfirm: (status: string, notes: string, acceptedBy?: string) => void;
}) {
  const allowed = ALLOWED_TRANSITIONS[currentCase.commercial_status] ?? [];
  const [nextStatus, setNextStatus] = useState(allowed[0] ?? '');
  const [notes, setNotes] = useState('');
  const [acceptedBy, setAcceptedBy] = useState('');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Update status</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Current status: <strong>{currentCase.commercial_status}</strong>
          </Typography>
          {allowed.length === 0 ? (
            <Alert severity="info">This case is in a terminal state and cannot be transitioned further.</Alert>
          ) : (
            <FormControl size="small" fullWidth>
              <InputLabel>New status</InputLabel>
              <Select
                value={nextStatus}
                label="New status"
                onChange={(e) => setNextStatus(e.target.value)}
              >
                {allowed.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {nextStatus === 'accepted' && (
            <TextField
              size="small"
              label="Accepted by"
              value={acceptedBy}
              onChange={(e) => setAcceptedBy(e.target.value)}
              fullWidth
            />
          )}
          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={!nextStatus || allowed.length === 0}
          onClick={() => {
            onConfirm(nextStatus, notes, acceptedBy || undefined);
            onClose();
          }}
        >
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Upload / create case dialog ────────────────────────────────────────────────

function UploadLineupDialog({
  open,
  onClose,
  activePlanId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  activePlanId: number | null;
  onCreated: () => void;
}) {
  const [periodLabel, setPeriodLabel] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [notes, setNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!activePlanId) return;
    setCreating(true);
    setError(null);
    try {
      await apiPost('/api/v1/commercial-planner/lineup-cases', {
        commercial_plan_id: activePlanId,
        period_label: periodLabel.trim() || null,
        currency_code: currencyCode.trim() || null,
        country_code: countryCode.trim() || null,
        notes: notes.trim() || null,
      });
      onCreated();
      onClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create lineup case';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Upload current lineup</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            size="small"
            label="Period label"
            value={periodLabel}
            onChange={(e) => setPeriodLabel(e.target.value)}
            placeholder="e.g. Q2 2026"
            fullWidth
          />
          <Stack direction="row" spacing={2}>
            <TextField
              size="small"
              label="Currency code"
              value={currencyCode}
              onChange={(e) => setCurrencyCode(e.target.value)}
              placeholder="e.g. USD"
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label="Country code"
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              placeholder="e.g. US"
              sx={{ flex: 1 }}
            />
          </Stack>
          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={handleCreate}
          disabled={creating}
          data-testid="upload-lineup-confirm"
        >
          {creating ? 'Creating…' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main section ──────────────────────────────────────────────────────────────

export function CurrentLineupSection({ activePlanId }: { activePlanId: number | null }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewLinesCase, setViewLinesCase] = useState<CommercialLineupCase | null>(null);
  const [statusCase, setStatusCase] = useState<CommercialLineupCase | null>(null);

  const { data: cases, isLoading } = useQuery<CommercialLineupCase[]>({
    queryKey: ['commercial-lineup-cases', activePlanId],
    queryFn: ({ signal }) =>
      apiGet<CommercialLineupCase[]>(
        `/api/v1/commercial-planner/lineup-cases?plan_id=${activePlanId}`,
        { signal }
      ),
    enabled: activePlanId != null,
  });

  const statusMutation = useMutation({
    mutationFn: ({
      caseId,
      status,
      notes,
      acceptedBy,
    }: {
      caseId: number;
      status: string;
      notes: string;
      acceptedBy?: string;
    }) =>
      apiPatch(`/api/v1/commercial-planner/lineup-cases/${caseId}/status`, {
        status,
        notes: notes || null,
        accepted_by: acceptedBy ?? null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (caseId: number) =>
      apiDelete(`/api/v1/commercial-planner/lineup-cases/${caseId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] }),
  });

  const count = cases?.length ?? 0;

  return (
    <>
      <Box sx={{ mb: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button
            size="small"
            variant="text"
            onClick={() => setExpanded((e) => !e)}
            endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            data-testid="current-lineup-section-toggle"
          >
            Current lineups
          </Button>
          {count > 0 && <Chip label={count} size="small" />}
          {activePlanId != null && (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setUploadOpen(true)}
              data-testid="upload-current-lineup-btn"
            >
              Upload current lineup
            </Button>
          )}
        </Stack>

        <Collapse in={expanded}>
          <Box sx={{ mt: 1 }}>
            {isLoading ? (
              <CircularProgress size={20} />
            ) : count === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No current lineup cases for this plan.
              </Typography>
            ) : (
              <Stack spacing={1}>
                {cases!.map((c) => (
                  <Box
                    key={c.id}
                    sx={{
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 1,
                      p: 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      flexWrap: 'wrap',
                    }}
                  >
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 120 }}>
                      {c.file_name ?? '(no file)'}
                      {c.period_label ? ` · ${c.period_label}` : ''}
                    </Typography>
                    <Chip
                      label={c.commercial_status}
                      size="small"
                      color={STATUS_COLORS[c.commercial_status] ?? 'default'}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {c.line_count} line{c.line_count === 1 ? '' : 's'}
                    </Typography>
                    <Button size="small" onClick={() => setViewLinesCase(c)}>
                      View lines
                    </Button>
                    {(ALLOWED_TRANSITIONS[c.commercial_status]?.length ?? 0) > 0 && (
                      <Button size="small" onClick={() => setStatusCase(c)}>
                        Update status
                      </Button>
                    )}
                    {c.commercial_status === 'draft_imported' && (
                      <Button
                        size="small"
                        color="error"
                        onClick={() => deleteMutation.mutate(c.id)}
                        disabled={deleteMutation.isPending}
                      >
                        Delete
                      </Button>
                    )}
                  </Box>
                ))}
              </Stack>
            )}
          </Box>
        </Collapse>
      </Box>

      <UploadLineupDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        activePlanId={activePlanId}
        onCreated={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
      />

      {viewLinesCase && (
        <CaseLinesDialog
          open={viewLinesCase != null}
          onClose={() => setViewLinesCase(null)}
          caseId={viewLinesCase.id}
          caseLabel={
            [viewLinesCase.file_name, viewLinesCase.period_label].filter(Boolean).join(' · ') ||
            `Case #${viewLinesCase.id}`
          }
        />
      )}

      {statusCase && (
        <StatusTransitionDialog
          open={statusCase != null}
          onClose={() => setStatusCase(null)}
          currentCase={statusCase}
          onConfirm={(status, notes, acceptedBy) => {
            statusMutation.mutate({ caseId: statusCase.id, status, notes, acceptedBy });
          }}
        />
      )}
    </>
  );
}

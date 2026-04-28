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
import { useEffect, useState } from 'react';

import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';

function formatHttpErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { message?: string; remediation?: string };
    const parts = [d.message, d.remediation].filter((x): x is string => Boolean(x));
    if (parts.length) return parts.join(' ');
  }
  if (Array.isArray(detail)) {
    return detail
      .map((e) =>
        typeof e === 'object' && e !== null && 'msg' in e
          ? String((e as { msg: unknown }).msg)
          : JSON.stringify(e),
      )
      .join('; ');
  }
  return 'unknown error';
}

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
  product_id: number | null;
  product_sku: string | null;
  product_name: string | null;
  product_part_number: string | null;
  product_model_name: string | null;
  product_sales_model_name: string | null;
  customer_id: number | null;
  customer_code: string | null;
  customer_name: string | null;
  distributor_id: number | null;
  distributor_code: string | null;
  distributor_name: string | null;
  customer_token: string | null;
  distributor_token_raw: string | null;
  sku_raw: string | null;
  part_number_raw: string | null;
  model_raw: string | null;
  quantity_units: number | null;
  msrp_local: number | null;
  promo_price_evidence_local: number | null;
  dap_evidence_local: number | null;
  diagnostic_codes: string[];
  row_status: string;
  dap_semantics_note?: string;
};

type CaseLinesResponse = {
  lines: CommercialLineupLine[];
  dap_semantics_note: string;
};

function lineupProductLabel(ln: CommercialLineupLine): string {
  const a =
    ln.product_sales_model_name?.trim() ||
    ln.product_model_name?.trim() ||
    ln.model_raw?.trim() ||
    ln.product_name?.trim() ||
    ln.product_sku?.trim() ||
    ln.sku_raw?.trim() ||
    ln.part_number_raw?.trim();
  return a || '—';
}

function lineupCustomerCell(ln: CommercialLineupLine): string {
  if (ln.customer_id != null) {
    const bits = [ln.customer_code, ln.customer_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  const t = ln.customer_token?.trim();
  if (t) return `${t} (unresolved)`;
  return '—';
}

function lineupDistributorCell(ln: CommercialLineupLine): string {
  if (ln.distributor_id != null) {
    const bits = [ln.distributor_code, ln.distributor_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  const t = (ln.distributor_token_raw ?? '').trim();
  if (t) return `${t} (unresolved)`;
  return '—';
}

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

// ── Types: sync ───────────────────────────────────────────────────────────────

type SyncPreview = {
  case_id: number;
  plan_id: number;
  total_lines: number;
  will_create: number;
  skipped_duplicates: number;
  skipped_unresolved: number;
  skipped_unresolved_product: number;
  skipped_missing_customer: number;
  skipped_missing_distributor: number;
  skipped_missing_quantity: number;
  skipped_missing_srp: number;
};

type SyncResult = {
  case_id: number;
  plan_id: number;
  created: number;
  skipped_duplicates: number;
  skipped_unresolved: number;
  skipped_unresolved_product: number;
  skipped_missing_customer: number;
  skipped_missing_distributor: number;
  skipped_missing_quantity: number;
  skipped_missing_srp: number;
  failed: number;
  created_line_ids: number[];
  warnings: string[];
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SyncPreviewDialog({
  open,
  onClose,
  caseItem,
  onSyncComplete,
}: {
  open: boolean;
  onClose: () => void;
  caseItem: CommercialLineupCase;
  onSyncComplete?: () => void;
}) {
  const qc = useQueryClient();
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const previewUrl = `/api/v1/commercial-planner/lineup-cases/${caseItem.id}/sync-to-plan/preview${
    caseItem.commercial_plan_id ? `?commercial_plan_id=${caseItem.commercial_plan_id}` : ''
  }`;

  const { data: preview, isLoading: previewLoading } = useQuery<SyncPreview>({
    queryKey: ['sync-to-plan-preview', caseItem.id, caseItem.commercial_plan_id],
    queryFn: ({ signal }) => apiGet<SyncPreview>(previewUrl, { signal }),
    enabled: open && !syncResult,
  });

  const syncMutation = useMutation({
    mutationFn: () =>
      apiPost<SyncResult>(`/api/v1/commercial-planner/lineup-cases/${caseItem.id}/sync-to-plan`, {
        commercial_plan_id: caseItem.commercial_plan_id ?? null,
      }),
    onSuccess: (result) => {
      setSyncResult(result);
      qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      onSyncComplete?.();
    },
    onError: (e: unknown) => {
      setSyncError(e instanceof Error ? e.message : 'Sync failed');
    },
  });

  const handleClose = () => {
    setSyncResult(null);
    setSyncError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Sync to plan</DialogTitle>
      <DialogContent>
        {syncResult ? (
          <Alert severity="success">
            <Typography variant="body2">
              Sync complete: <strong>{syncResult.created}</strong> line
              {syncResult.created !== 1 ? 's' : ''} created.
            </Typography>
            {syncResult.skipped_duplicates > 0 && (
              <Typography variant="body2">
                Skipped {syncResult.skipped_duplicates} duplicate(s).
              </Typography>
            )}
            {syncResult.skipped_unresolved_product != null && syncResult.skipped_unresolved_product > 0 && (
              <Typography variant="body2">
                Skipped — unresolved product: {syncResult.skipped_unresolved_product}
              </Typography>
            )}
            {syncResult.skipped_missing_customer != null && syncResult.skipped_missing_customer > 0 && (
              <Typography variant="body2">
                Skipped — missing customer (use fallback or fix file): {syncResult.skipped_missing_customer}
              </Typography>
            )}
            {syncResult.skipped_missing_distributor != null && syncResult.skipped_missing_distributor > 0 && (
              <Typography variant="body2">
                Skipped — missing distributor (use fallback or fix file): {syncResult.skipped_missing_distributor}
              </Typography>
            )}
            {syncResult.skipped_missing_quantity != null && syncResult.skipped_missing_quantity > 0 && (
              <Typography variant="body2">
                Skipped — missing quantity: {syncResult.skipped_missing_quantity}
              </Typography>
            )}
            {syncResult.skipped_unresolved > 0 && (
              <Typography variant="body2" color="text.secondary">
                Total blocked rows (excl. duplicates / missing SRP): {syncResult.skipped_unresolved}
              </Typography>
            )}
            {syncResult.skipped_missing_srp > 0 && (
              <Typography variant="body2">
                Skipped {syncResult.skipped_missing_srp} missing SRP.
              </Typography>
            )}
            {syncResult.warnings.length > 0 && (
              <Typography variant="body2">
                Warnings: {syncResult.warnings.join('; ')}
              </Typography>
            )}
          </Alert>
        ) : syncError ? (
          <Alert severity="error">{syncError}</Alert>
        ) : previewLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={28} />
          </Box>
        ) : preview ? (
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <Typography variant="body2">
              Total lines in case: <strong>{preview.total_lines}</strong>
            </Typography>
            <Typography variant="body2" color="success.main">
              Eligible (will be created): <strong>{preview.will_create}</strong>
            </Typography>
            {preview.skipped_duplicates > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — already in plan: {preview.skipped_duplicates}
              </Typography>
            )}
            {preview.skipped_unresolved_product != null && preview.skipped_unresolved_product > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — unresolved product: {preview.skipped_unresolved_product}
              </Typography>
            )}
            {preview.skipped_missing_customer != null && preview.skipped_missing_customer > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — missing customer: {preview.skipped_missing_customer}
              </Typography>
            )}
            {preview.skipped_missing_distributor != null && preview.skipped_missing_distributor > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — missing distributor: {preview.skipped_missing_distributor}
              </Typography>
            )}
            {preview.skipped_missing_quantity != null && preview.skipped_missing_quantity > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — missing quantity: {preview.skipped_missing_quantity}
              </Typography>
            )}
            {preview.skipped_unresolved > 0 && (
              <Typography variant="body2" color="text.secondary">
                Total blocked (excl. duplicates / missing SRP): {preview.skipped_unresolved}
              </Typography>
            )}
            {preview.skipped_missing_srp > 0 && (
              <Typography variant="body2" color="text.secondary">
                Skipped — missing SRP: {preview.skipped_missing_srp}
              </Typography>
            )}
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          {syncResult ? 'Close' : 'Cancel'}
        </Button>
        {!syncResult && (
          <Button
            size="small"
            variant="contained"
            disabled={syncMutation.isPending || previewLoading || !preview}
            onClick={() => syncMutation.mutate()}
            data-testid="sync-to-plan-confirm"
          >
            {syncMutation.isPending ? 'Syncing…' : 'Sync to plan'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

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
                  <TableCell>Model / product</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell>Part #</TableCell>
                  <TableCell>Customer</TableCell>
                  <TableCell>Distributor</TableCell>
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
                      <Typography variant="body2">{lineupProductLabel(ln)}</Typography>
                      {ln.product_sku && ln.sku_raw && ln.product_sku !== ln.sku_raw && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          SKU raw: {ln.sku_raw}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {ln.product_sku ?? ln.sku_raw ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>{ln.product_part_number ?? ln.part_number_raw ?? '—'}</TableCell>
                    <TableCell>{lineupCustomerCell(ln)}</TableCell>
                    <TableCell>{lineupDistributorCell(ln)}</TableCell>
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

// ── Retry parse on empty draft case ───────────────────────────────────────────

function RetryParseDialog({
  open,
  onClose,
  targetCase,
  onParsed,
}: {
  open: boolean;
  onClose: () => void;
  targetCase: CommercialLineupCase;
  onParsed: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    setFile(null);
    setError(null);
    onClose();
  };

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const parseRes = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${targetCase.id}/parse-upload`,
        { method: 'POST', body: fd },
      );
      if (!parseRes.ok) {
        const errBody = await parseRes.json().catch(() => ({}));
        setError(
          `Parse failed. ${formatHttpErrorDetail(errBody.detail)} You can fix the file and try again.`,
        );
        return;
      }
      onParsed();
      handleClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Upload file — case #{targetCase.id}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            This case has no lines yet. Choose a lineup file (.csv, .xlsx, .xlsm) to parse into the case.
          </Typography>
          <Button variant="outlined" component="label" size="small">
            {file ? file.name : 'Choose file…'}
            <input
              type="file"
              hidden
              accept=".csv,.xlsx,.xlsm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={handleSubmit}
          disabled={!file || uploading}
          data-testid="retry-parse-confirm"
        >
          {uploading ? 'Uploading…' : 'Parse file'}
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
  planCountryCode,
  planCurrencyCode,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  activePlanId: number | null;
  planCountryCode?: string | null;
  planCurrencyCode?: string | null;
  onCreated: () => void;
}) {
  const [periodLabel, setPeriodLabel] = useState('');
  const [currencyCode, setCurrencyCode] = useState('ZAR');
  const [countryCode, setCountryCode] = useState('ZA');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const cc = (planCountryCode ?? '').trim() || 'ZA';
    const cur = (planCurrencyCode ?? '').trim() || 'ZAR';
    setCountryCode(cc.length <= 3 ? cc.toUpperCase() : 'ZA');
    setCurrencyCode(['ZAR', 'USD'].includes(cur.toUpperCase()) ? cur.toUpperCase() : 'ZAR');
  }, [open, planCountryCode, planCurrencyCode]);

  const handleClose = () => {
    setFile(null);
    setError(null);
    setPeriodLabel('');
    setNotes('');
    onClose();
  };

  const handleCreate = async () => {
    if (!activePlanId) return;
    setCreating(true);
    setError(null);
    try {
      const caseResponse = await apiPost<{ id: number }>('/api/v1/commercial-planner/lineup-cases', {
        commercial_plan_id: activePlanId,
        period_label: periodLabel.trim() || null,
        currency_code: currencyCode,
        country_code: countryCode,
        notes: notes.trim() || null,
      });

      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        const parseRes = await fetch(
          `/api/v1/commercial-planner/lineup-cases/${caseResponse.id}/parse-upload`,
          { method: 'POST', body: fd },
        );
        if (!parseRes.ok) {
          const errBody = await parseRes.json().catch(() => ({}));
          setError(
            `Case created (id=${caseResponse.id}) but file parse failed. ` +
              `The draft case has no lines yet — use "Upload file to this case" on the case card to retry, or delete the draft. ` +
              formatHttpErrorDetail(errBody.detail),
          );
          return;
        }
      }

      onCreated();
      handleClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create lineup case';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
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
          <Typography variant="caption" color="text.secondary" display="block">
            Country and currency describe this uploaded lineup (metadata only; no FX conversion here).
          </Typography>
          <Stack direction="row" spacing={2}>
            <FormControl size="small" sx={{ flex: 1 }} data-testid="upload-lineup-country">
              <InputLabel id="upload-lineup-country-label">Country</InputLabel>
              <Select
                labelId="upload-lineup-country-label"
                label="Country"
                value={countryCode}
                onChange={(e) => setCountryCode(String(e.target.value))}
              >
                <MenuItem value="ZA">ZA</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ flex: 1 }} data-testid="upload-lineup-currency">
              <InputLabel id="upload-lineup-currency-label">Currency</InputLabel>
              <Select
                labelId="upload-lineup-currency-label"
                label="Currency"
                value={currencyCode}
                onChange={(e) => setCurrencyCode(String(e.target.value))}
              >
                <MenuItem value="ZAR">ZAR</MenuItem>
                <MenuItem value="USD">USD</MenuItem>
              </Select>
            </FormControl>
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
          <Box>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              Lineup file (optional — can be uploaded after case creation)
            </Typography>
            <Button variant="outlined" component="label" size="small">
              {file ? file.name : 'Choose file…'}
              <input
                type="file"
                hidden
                accept=".csv,.xlsx,.xlsm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>
          </Box>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
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

function LineupLineNumericEditor({
  disabled,
  initial,
  onCommit,
  width,
}: {
  disabled?: boolean;
  initial: number | null;
  onCommit: (next: number | null) => void;
  width: number;
}) {
  const [text, setText] = useState(initial != null ? String(initial) : '');
  useEffect(() => {
    setText(initial != null ? String(initial) : '');
  }, [initial]);
  return (
    <TextField
      size="small"
      type="number"
      disabled={disabled}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const t = text.trim();
        if (t === '') {
          onCommit(null);
          return;
        }
        const n = Number(t);
        if (!Number.isFinite(n)) return;
        onCommit(n);
      }}
      sx={{ width }}
    />
  );
}

// ── Main section ──────────────────────────────────────────────────────────────

export function CurrentLineupSection({
  activePlanId,
  planLineCount = 0,
  planCountryCode,
  planCurrencyCode,
  onSyncComplete,
  onStagedLineupSummary,
}: {
  activePlanId: number | null;
  planLineCount?: number;
  planCountryCode?: string | null;
  planCurrencyCode?: string | null;
  onSyncComplete?: () => void;
  onStagedLineupSummary?: (summary: { caseId: number | null; lineCount: number }) => void;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewLinesCase, setViewLinesCase] = useState<CommercialLineupCase | null>(null);
  const [statusCase, setStatusCase] = useState<CommercialLineupCase | null>(null);
  const [syncCase, setSyncCase] = useState<CommercialLineupCase | null>(null);
  const [retryParseCase, setRetryParseCase] = useState<CommercialLineupCase | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<number | null>(null);

  const { data: cases, isLoading } = useQuery<CommercialLineupCase[]>({
    queryKey: ['commercial-lineup-cases', activePlanId],
    queryFn: ({ signal }) =>
      apiGet<CommercialLineupCase[]>(
        `/api/v1/commercial-planner/lineup-cases?plan_id=${activePlanId}`,
        { signal }
      ),
    enabled: activePlanId != null,
  });

  useEffect(() => {
    if (!cases?.length) {
      setActiveCaseId(null);
      return;
    }
    setActiveCaseId((prev) => {
      if (prev != null && cases.some((c) => c.id === prev)) return prev;
      const preferred = cases.find((c) => c.line_count > 0) ?? cases[0];
      return preferred?.id ?? null;
    });
  }, [cases]);

  const { data: workingLinesData } = useQuery<CaseLinesResponse>({
    queryKey: ['commercial-lineup-case-lines', activeCaseId],
    queryFn: ({ signal }) =>
      apiGet<CaseLinesResponse>(
        `/api/v1/commercial-planner/lineup-cases/${activeCaseId}/lines`,
        { signal }
      ),
    enabled: activeCaseId != null && activePlanId != null,
  });

  const workingLines = workingLinesData?.lines ?? [];
  const activeCase = cases?.find((c) => c.id === activeCaseId);

  useEffect(() => {
    onStagedLineupSummary?.({ caseId: activeCaseId, lineCount: workingLines.length });
  }, [activeCaseId, workingLines.length, onStagedLineupSummary]);

  const patchLineMutation = useMutation({
    mutationFn: async (payload: {
      caseId: number;
      lineId: number;
      body: { quantity_units?: number | null; msrp_local?: number | null; promo_price_evidence_local?: number | null };
    }) => {
      await apiPatch(
        `/api/v1/commercial-planner/lineup-cases/${payload.caseId}/lines/${payload.lineId}`,
        payload.body
      );
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', activeCaseId] });
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] });
    },
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
                      borderColor: activeCaseId === c.id ? 'primary.main' : 'divider',
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
                    <Button
                      size="small"
                      variant={activeCaseId === c.id ? 'contained' : 'outlined'}
                      onClick={() => setActiveCaseId(c.id)}
                      data-testid={`lineup-workbench-${c.id}`}
                    >
                      Workbench
                    </Button>
                    <Button size="small" onClick={() => setViewLinesCase(c)}>
                      Details
                    </Button>
                    {c.commercial_status === 'draft_imported' && c.line_count === 0 && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setRetryParseCase(c)}
                        data-testid={`retry-parse-open-${c.id}`}
                      >
                        Upload file to this case
                      </Button>
                    )}
                    {(ALLOWED_TRANSITIONS[c.commercial_status]?.length ?? 0) > 0 && (
                      <Button size="small" onClick={() => setStatusCase(c)}>
                        Update status
                      </Button>
                    )}
                    {c.commercial_status === 'accepted' && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="primary"
                        onClick={() => setSyncCase(c)}
                        data-testid="sync-to-plan-btn"
                      >
                        Sync to plan
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

        {activeCaseId != null && activeCase && (
          <Box sx={{ mt: 2 }} data-testid="current-lineup-working-grid">
            {planLineCount === 0 && workingLines.length > 0 && (
              <Alert severity="info" sx={{ mb: 1 }}>
                Current lineup rows are staged for this plan. Accept the case and sync to plan to create planner
                lines.
              </Alert>
            )}
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Current lineup working rows — case #{activeCase.id}
              {activeCase.file_name ? ` · ${activeCase.file_name}` : ''}
            </Typography>
            {workingLines.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No rows in the selected case yet. Upload a file or choose another case.
              </Typography>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>#</TableCell>
                      <TableCell>Model / product</TableCell>
                      <TableCell>SKU</TableCell>
                      <TableCell>Part #</TableCell>
                      <TableCell>Customer</TableCell>
                      <TableCell>Distributor</TableCell>
                      <TableCell>Units</TableCell>
                      <TableCell>MSRP / list</TableCell>
                      <TableCell>Promo evidence</TableCell>
                      <TableCell>DAP evidence</TableCell>
                      <TableCell>Status / issues</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {workingLines.map((ln) => {
                      const canEdit = activeCase.commercial_status === 'draft_imported';
                      const issues =
                        (ln.diagnostic_codes?.length && ln.diagnostic_codes.join(', ')) || ln.row_status;
                      return (
                        <TableRow key={ln.id}>
                          <TableCell>{ln.source_row_number ?? ln.id}</TableCell>
                          <TableCell>
                            <Typography variant="body2">{lineupProductLabel(ln)}</Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontFamily="monospace">
                              {ln.product_sku ?? ln.sku_raw ?? '—'}
                            </Typography>
                          </TableCell>
                          <TableCell>{ln.product_part_number ?? ln.part_number_raw ?? '—'}</TableCell>
                          <TableCell>{lineupCustomerCell(ln)}</TableCell>
                          <TableCell>{lineupDistributorCell(ln)}</TableCell>
                          <TableCell>
                            <LineupLineNumericEditor
                              disabled={!canEdit || patchLineMutation.isPending}
                              initial={ln.quantity_units}
                              width={88}
                              onCommit={(next) => {
                                if (!canEdit || next == null || !activeCaseId) return;
                                if (next === ln.quantity_units) return;
                                patchLineMutation.mutate({
                                  caseId: activeCaseId,
                                  lineId: ln.id,
                                  body: { quantity_units: next },
                                });
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <LineupLineNumericEditor
                              disabled={!canEdit || patchLineMutation.isPending}
                              initial={ln.msrp_local}
                              width={100}
                              onCommit={(next) => {
                                if (!canEdit || next == null || !activeCaseId) return;
                                if (next === ln.msrp_local) return;
                                patchLineMutation.mutate({
                                  caseId: activeCaseId,
                                  lineId: ln.id,
                                  body: { msrp_local: next },
                                });
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <LineupLineNumericEditor
                              disabled={!canEdit || patchLineMutation.isPending}
                              initial={ln.promo_price_evidence_local}
                              width={100}
                              onCommit={(next) => {
                                if (!canEdit || next == null || !activeCaseId) return;
                                if (next === ln.promo_price_evidence_local) return;
                                patchLineMutation.mutate({
                                  caseId: activeCaseId,
                                  lineId: ln.id,
                                  body: { promo_price_evidence_local: next },
                                });
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            {ln.dap_evidence_local != null ? ln.dap_evidence_local.toLocaleString() : '—'}
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">{issues}</Typography>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Box>
        )}
      </Box>

      <UploadLineupDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        activePlanId={activePlanId}
        planCountryCode={planCountryCode}
        planCurrencyCode={planCurrencyCode}
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

      {syncCase && (
        <SyncPreviewDialog
          open={syncCase != null}
          onClose={() => setSyncCase(null)}
          caseItem={syncCase}
          onSyncComplete={onSyncComplete}
        />
      )}

      {retryParseCase && (
        <RetryParseDialog
          open={retryParseCase != null}
          onClose={() => setRetryParseCase(null)}
          targetCase={retryParseCase}
          onParsed={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
        />
      )}
    </>
  );
}

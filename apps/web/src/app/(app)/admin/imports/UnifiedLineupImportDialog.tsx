'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
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
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';
import { apiGet, apiPostFormData, safeDisplayError } from '@/lib/api';

const ACCEPT =
  '.csv,.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,text/csv';

const ALLOWED_EXT = ['.csv', '.xlsx', '.xlsm'];

type PlanRow = {
  id: number;
  plan_name: string | null;
  country_code: string | null;
  currency_code: string | null;
};

type UnifiedImportFileResult = {
  filename: string;
  case_id?: number;
  import_job_id?: number;
  outcome?: string;
  task_id?: string;
  error?: string;
};

type UnifiedImportResponse = {
  files: UnifiedImportFileResult[];
  file_count: number;
  dispatched: number;
};

function outcomeChip(r: UnifiedImportFileResult) {
  if (r.outcome === 'enqueued') return <Chip size="small" color="success" label="Queued" />;
  if (r.outcome === 'dispatch_failed') return <Chip size="small" color="warning" label="Dispatch failed" />;
  if (r.outcome === 'error') return <Chip size="small" color="error" label="Error" />;
  return <Chip size="small" variant="outlined" label={r.outcome ?? 'Unknown'} />;
}

export type UnifiedLineupImportDialogProps = {
  open: boolean;
  onClose: () => void;
};

/**
 * Import-Centre surface for the first-class unified (multi-file) lineup importer.
 *
 * Posts to `POST /api/v1/commercial-planner/lineup/unified-import` (multipart: repeated `files`
 * field + shared `commercial_plan_id` / `period_label` / `country_code` / `currency_code`). The
 * backend fans out one CommercialLineupCase + one always-async parse job per file; this dialog
 * registers each returned Celery `task_id` with the activity-feed (nav bell) so per-file progress
 * is visible, and shows the per-file dispatch outcome inline.
 *
 * The `unified_lineup` template is `hidden=true` (dedicated surface, not the generic wizard), so
 * this dialog is opened from an explicit Import-Centre card rather than the template grid.
 */
export function UnifiedLineupImportDialog({ open, onClose }: UnifiedLineupImportDialogProps) {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [planId, setPlanId] = useState<number | ''>('');
  const [periodLabel, setPeriodLabel] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [results, setResults] = useState<UnifiedImportResponse | null>(null);

  const { data: plans } = useQuery({
    queryKey: ['commercial-planner', 'plans'],
    queryFn: ({ signal }) => apiGet<PlanRow[]>('/api/v1/commercial-planner/plans', { signal }),
    enabled: open,
  });

  const addFiles = useCallback((incoming: FileList | File[] | null | undefined) => {
    if (!incoming) return;
    const next: File[] = [];
    for (const f of Array.from(incoming)) {
      const lower = f.name.toLowerCase();
      if (ALLOWED_EXT.some((ext) => lower.endsWith(ext))) next.push(f);
    }
    if (!next.length) return;
    setFiles((prev) => {
      const seen = new Set(prev.map((p) => `${p.name}:${p.size}`));
      const merged = [...prev];
      for (const f of next) {
        const key = `${f.name}:${f.size}`;
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(f);
        }
      }
      return merged;
    });
  }, []);

  const removeFile = useCallback((idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const handlePlanChange = useCallback(
    (value: number | '') => {
      setPlanId(value);
      if (value === '') return;
      const plan = (plans ?? []).find((p) => p.id === value);
      if (!plan) return;
      // Prefill country/currency from the selected plan only when the user has not set them.
      setCountryCode((cur) => cur || (plan.country_code ?? ''));
      setCurrencyCode((cur) => cur || (plan.currency_code ?? ''));
    },
    [plans]
  );

  const upload = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      for (const f of files) fd.append('files', f);
      if (planId !== '') fd.append('commercial_plan_id', String(planId));
      if (periodLabel.trim()) fd.append('period_label', periodLabel.trim());
      if (countryCode.trim()) fd.append('country_code', countryCode.trim().toUpperCase());
      if (currencyCode.trim()) fd.append('currency_code', currencyCode.trim().toUpperCase());
      return apiPostFormData<UnifiedImportResponse>(
        '/api/v1/commercial-planner/lineup/unified-import',
        fd
      );
    },
    onSuccess: (res) => {
      setResults(res);
      for (const r of res.files) {
        if (r.outcome === 'enqueued' && r.task_id && r.import_job_id != null) {
          registerClientBackgroundTask({
            taskId: r.task_id,
            importJobId: r.import_job_id,
            kind: 'commercial_planner_lineup_parse',
            label: `Parsing ${r.filename}`,
          });
        }
      }
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      if (planId !== '') {
        void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', planId] });
      }
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      // Clear the staged file list; results table summarises what was dispatched.
      setFiles([]);
    },
  });

  const totalSize = useMemo(() => files.reduce((acc, f) => acc + f.size, 0), [files]);

  const handleClose = useCallback(() => {
    if (upload.isPending) return;
    onClose();
    // Reset transient state for the next open (keep plan/metadata for convenience-free fresh start).
    setResults(null);
    setFiles([]);
    upload.reset();
  }, [onClose, upload]);

  const canSubmit = files.length > 0 && !upload.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>Unified lineup import (multi-file)</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Alert severity="info">
            Upload one or more lineup files (.csv / .xlsx / .xlsm). Each file becomes its own lineup
            case and is parsed asynchronously with the full backwards pricing chain (SRP&rarr;DAP) and
            period / product-line inference. Watch per-file progress in the activity feed (bell icon).
            DAP stays evidence-only &mdash; it is never written to controlled cost.
          </Alert>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <FormControl size="small" sx={{ minWidth: 240, flex: 1 }}>
              <InputLabel id="unified-plan-label">Commercial plan (optional)</InputLabel>
              <Select
                labelId="unified-plan-label"
                label="Commercial plan (optional)"
                value={planId}
                onChange={(e) =>
                  handlePlanChange(e.target.value === '' ? '' : Number(e.target.value))
                }
                data-testid="unified-import-plan-select"
              >
                <MenuItem value="">
                  <em>None (unlinked)</em>
                </MenuItem>
                {(plans ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.plan_name ? `${p.plan_name} (#${p.id})` : `Plan #${p.id}`}
                    {p.currency_code ? ` · ${p.currency_code}` : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              size="small"
              label="Period label"
              placeholder="e.g. 26Q1"
              value={periodLabel}
              onChange={(e) => setPeriodLabel(e.target.value)}
              sx={{ flex: 1 }}
              data-testid="unified-import-period"
            />
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              size="small"
              label="Country code"
              placeholder="e.g. ZA"
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              sx={{ flex: 1 }}
              inputProps={{ maxLength: 8, style: { textTransform: 'uppercase' } }}
              data-testid="unified-import-country"
            />
            <TextField
              size="small"
              label="Currency code"
              placeholder="e.g. ZAR"
              value={currencyCode}
              onChange={(e) => setCurrencyCode(e.target.value)}
              sx={{ flex: 1 }}
              inputProps={{ maxLength: 8, style: { textTransform: 'uppercase' } }}
              data-testid="unified-import-currency"
            />
          </Stack>

          <Box
            onDragEnter={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              addFiles(e.dataTransfer.files);
            }}
            sx={{
              border: '2px dashed',
              borderColor: dragActive ? 'primary.main' : 'divider',
              borderRadius: 2,
              px: 3,
              py: 3,
              textAlign: 'center',
              bgcolor: dragActive ? 'action.selected' : 'action.hover',
            }}
            data-testid="unified-import-dropzone"
          >
            <CloudUploadOutlinedIcon sx={{ fontSize: 36, color: 'primary.main', mb: 1 }} />
            <Typography variant="subtitle1" fontWeight={600}>
              Drop lineup files here
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Or choose multiple files. CSV / XLSX / XLSM.
            </Typography>
            <Button
              variant="contained"
              component="label"
              disabled={upload.isPending}
              data-testid="unified-import-choose"
            >
              Choose files
              <input
                ref={fileInputRef}
                hidden
                type="file"
                multiple
                accept={ACCEPT}
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = '';
                }}
              />
            </Button>
          </Box>

          {files.length > 0 ? (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {files.length} file{files.length === 1 ? '' : 's'} selected ·{' '}
                {(totalSize / 1024).toFixed(0)} KB
              </Typography>
              <Stack spacing={0.5}>
                {files.map((f, idx) => (
                  <Stack
                    key={`${f.name}:${f.size}:${idx}`}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ px: 1, py: 0.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
                  >
                    <Typography variant="body2" sx={{ flex: 1 }} noWrap title={f.name}>
                      {f.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {(f.size / 1024).toFixed(0)} KB
                    </Typography>
                    <Tooltip title="Remove">
                      <IconButton
                        size="small"
                        onClick={() => removeFile(idx)}
                        disabled={upload.isPending}
                        data-testid={`unified-import-remove-${idx}`}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                ))}
              </Stack>
            </Box>
          ) : null}

          {upload.isPending ? <LinearProgress data-testid="unified-import-pending" /> : null}
          {upload.isError ? (
            <Alert severity="error" data-testid="unified-import-error">
              {safeDisplayError(upload.error)}
            </Alert>
          ) : null}

          {results ? (
            <Box data-testid="unified-import-results">
              <Alert severity={results.dispatched === results.file_count ? 'success' : 'warning'} sx={{ mb: 1 }}>
                Dispatched {results.dispatched} of {results.file_count} file
                {results.file_count === 1 ? '' : 's'}. Track parsing progress in the activity feed
                (bell icon); parsed cases appear under the plan&apos;s Current lineups.
              </Alert>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>File</TableCell>
                    <TableCell>Outcome</TableCell>
                    <TableCell>Case</TableCell>
                    <TableCell>Detail</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results.files.map((r, idx) => (
                    <TableRow key={`${r.filename}:${idx}`}>
                      <TableCell>
                        <Typography variant="body2" noWrap title={r.filename} sx={{ maxWidth: 240 }}>
                          {r.filename}
                        </Typography>
                      </TableCell>
                      <TableCell>{outcomeChip(r)}</TableCell>
                      <TableCell>{r.case_id != null ? `#${r.case_id}` : '—'}</TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">
                          {r.error ?? (r.import_job_id != null ? `Job #${r.import_job_id}` : '—')}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={upload.isPending}>
          {results ? 'Close' : 'Cancel'}
        </Button>
        <Button
          variant="contained"
          onClick={() => upload.mutate()}
          disabled={!canSubmit}
          startIcon={upload.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
          data-testid="unified-import-submit"
        >
          {upload.isPending ? 'Uploading…' : `Import ${files.length || ''} file${files.length === 1 ? '' : 's'}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

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
  Typography,
} from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { apiUrl, readFetchError, safeDisplayError } from '@/lib/api';

const DEMO_HEADERS = { 'X-User-Role': 'admin', 'X-User-Id': 'demo-user' };

const ACCEPT =
  '.csv,.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,text/csv';

const ALLOWED_EXT = ['.csv', '.xlsx', '.xlsm'];

type BatchGroupPreview = {
  signature: string;
  files: {
    filename: string;
    signature: string;
    column_count: number;
    sheet_count: number;
    unmappable: boolean;
    unmappable_reason?: string | null;
  }[];
};

type BatchProposeResponse = {
  group_count: number;
  file_count: number;
  groups: BatchGroupPreview[];
};

type BatchJobResult = {
  signature: string;
  outcome: 'created' | 'error';
  import_job_id?: number;
  stage?: string | null;
  filenames: string[];
  file_count?: number;
  error?: string;
};

type BatchJobsResponse = {
  group_count: number;
  groups_preview: BatchGroupPreview[];
  jobs: BatchJobResult[];
};

export type DsiBulkUploadDialogProps = {
  open: boolean;
  onClose: () => void;
  sourceId: number | null;
  dsiWorkflowMode: 'auto' | 'historical' | 'weekly';
  onWorkflowModeChange: (mode: 'auto' | 'historical' | 'weekly') => void;
  /** First created batch job id — wizard continues with unified mapping/steward. */
  onJobsCreated: (jobIds: number[]) => void;
};

function extOk(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXT.some((e) => lower.endsWith(e));
}

/**
 * Unified multi-file DSI upload: files with matching layouts → one import job;
 * divergent layouts → separate jobs (shown in group preview before upload).
 */
export function DsiBulkUploadDialog({
  open,
  onClose,
  sourceId,
  dsiWorkflowMode,
  onWorkflowModeChange,
  onJobsCreated,
}: DsiBulkUploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<BatchProposeResponse | null>(null);
  const [results, setResults] = useState<BatchJobsResponse | null>(null);

  const addFiles = useCallback((list: FileList | File[] | null) => {
    if (!list) return;
    const incoming = Array.from(list).filter((f) => extOk(f.name));
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name.toLowerCase()));
      const next = [...prev];
      for (const f of incoming) {
        if (!names.has(f.name.toLowerCase())) {
          next.push(f);
          names.add(f.name.toLowerCase());
        }
      }
      return next;
    });
    setPreview(null);
    setResults(null);
  }, []);

  const removeAt = useCallback((idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setPreview(null);
    setResults(null);
  }, []);

  const canPropose = sourceId != null && files.length > 0;
  const canUpload = canPropose && preview != null;

  const propose = useMutation({
    mutationFn: async (): Promise<BatchProposeResponse> => {
      if (sourceId == null) throw new Error('Select a DSI source first');
      const fd = new FormData();
      for (const file of files) {
        fd.append('files', file);
      }
      const res = await fetch(apiUrl('/api/v1/imports/dsi/batch-propose'), {
        method: 'POST',
        headers: DEMO_HEADERS,
        body: fd,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return (await res.json()) as BatchProposeResponse;
    },
    onSuccess: (data) => setPreview(data),
  });

  const upload = useMutation({
    mutationFn: async (): Promise<BatchJobsResponse> => {
      if (sourceId == null) throw new Error('Select a DSI source first');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      fd.append('dsi_workflow_mode', dsiWorkflowMode);
      for (const file of files) {
        fd.append('files', file);
      }
      const res = await fetch(apiUrl('/api/v1/imports/dsi/batch-jobs'), {
        method: 'POST',
        headers: DEMO_HEADERS,
        body: fd,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return (await res.json()) as BatchJobsResponse;
    },
    onSuccess: (data) => {
      setResults(data);
      const ids = data.jobs
        .filter((j) => j.outcome === 'created' && j.import_job_id != null)
        .map((j) => j.import_job_id as number);
      if (ids.length) onJobsCreated(ids);
    },
  });

  const createdCount = useMemo(
    () => (results?.jobs ?? []).filter((r) => r.outcome === 'created').length,
    [results]
  );

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="dsi-bulk-upload-dialog">
      <DialogTitle>DSI unified batch upload</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Files with the same column layout are combined into <strong>one import job</strong> — one
            mapping, one steward pass, one apply. Different layouts are split into separate jobs (shown
            below before upload).
          </Typography>
          <FormControl size="small" sx={{ maxWidth: 420 }}>
            <InputLabel id="dsi-bulk-workflow-mode-label">DSI workflow mode</InputLabel>
            <Select
              labelId="dsi-bulk-workflow-mode-label"
              label="DSI workflow mode"
              value={dsiWorkflowMode}
              onChange={(e) =>
                onWorkflowModeChange(e.target.value as 'auto' | 'historical' | 'weekly')
              }
            >
              <MenuItem value="auto">Auto — detect from transaction dates</MenuItem>
              <MenuItem value="historical">Historical (relaxed)</MenuItem>
              <MenuItem value="weekly">Weekly (strict)</MenuItem>
            </Select>
          </FormControl>
          {sourceId == null ? (
            <Alert severity="warning">Select a provider/source before uploading.</Alert>
          ) : null}
          <Box
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              addFiles(e.dataTransfer.files);
            }}
            sx={{
              border: '1px dashed',
              borderColor: 'divider',
              borderRadius: 1,
              p: 2,
              textAlign: 'center',
            }}
            data-testid="dsi-bulk-dropzone"
          >
            <CloudUploadOutlinedIcon color="action" sx={{ mb: 1 }} />
            <Typography variant="body2" gutterBottom>
              Drop CSV / XLSX files here, or choose files
            </Typography>
            <Button
              size="small"
              variant="outlined"
              onClick={() => inputRef.current?.click()}
              disabled={propose.isPending || upload.isPending}
            >
              Choose files
            </Button>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              hidden
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </Box>
          {files.length ? (
            <Table size="small" data-testid="dsi-bulk-file-list">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell width={80} />
                </TableRow>
              </TableHead>
              <TableBody>
                {files.map((f, i) => (
                  <TableRow key={`${f.name}-${i}`}>
                    <TableCell>{f.name}</TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        aria-label={`remove ${f.name}`}
                        onClick={() => removeAt(i)}
                        disabled={propose.isPending || upload.isPending}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
          {canPropose && !preview ? (
            <Button
              variant="outlined"
              onClick={() => void propose.mutateAsync()}
              disabled={propose.isPending}
              data-testid="dsi-bulk-preview-groups"
            >
              Preview batch groups
            </Button>
          ) : null}
          {propose.isPending ? <LinearProgress /> : null}
          {propose.isError ? <Alert severity="error">{safeDisplayError(propose.error)}</Alert> : null}
          {preview ? (
            <Stack spacing={1} data-testid="dsi-bulk-group-preview">
              <Alert severity="info">
                {preview.file_count} file{preview.file_count === 1 ? '' : 's'} →{' '}
                {preview.group_count} job{preview.group_count === 1 ? '' : 's'}
              </Alert>
              {preview.groups.map((g) => {
                const unmappableFiles = g.files.filter((f) => f.unmappable);
                const reasonCounts = unmappableFiles.reduce<Record<string, number>>((acc, f) => {
                  const r = f.unmappable_reason || 'no_dsi_headers';
                  acc[r] = (acc[r] || 0) + 1;
                  return acc;
                }, {});
                const reasonLabel =
                  unmappableFiles.length === 0
                    ? null
                    : Object.entries(reasonCounts)
                        .map(([reason, n]) => {
                          if (reason === 'no_dsi_headers') {
                            return `${n} file${n === 1 ? '' : 's'} don't look like DSI sellout/SOH (no header row found)`;
                          }
                          if (reason === 'empty') return `${n} empty file${n === 1 ? '' : 's'}`;
                          if (reason === 'parse_error') return `${n} could not be parsed`;
                          return `${n} unmappable (${reason})`;
                        })
                        .join('; ');
                return (
                  <Box
                    key={g.signature}
                    sx={{
                      border: 1,
                      borderColor: unmappableFiles.length ? 'error.main' : 'divider',
                      borderRadius: 1,
                      p: 1.5,
                    }}
                  >
                    <Typography variant="subtitle2" gutterBottom>
                      {unmappableFiles.length
                        ? `Skipped · not DSI-mappable (${unmappableFiles.length})`
                        : `Job group · signature ${g.signature}`}
                    </Typography>
                    {reasonLabel ? (
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                        {reasonLabel}
                      </Typography>
                    ) : null}
                    <Stack direction="row" flexWrap="wrap" gap={0.5}>
                      {g.files.map((f) => (
                        <Chip
                          key={f.filename}
                          size="small"
                          label={f.filename}
                          color={f.unmappable ? 'error' : 'default'}
                          variant="outlined"
                        />
                      ))}
                    </Stack>
                  </Box>
                );
              })}
            </Stack>
          ) : null}
          {upload.isPending ? <LinearProgress /> : null}
          {upload.isError ? <Alert severity="error">{safeDisplayError(upload.error)}</Alert> : null}
          {results ? (
            <Stack spacing={1} data-testid="dsi-bulk-results">
              <Alert severity={createdCount ? 'success' : 'warning'}>
                Created {createdCount} batch job{createdCount === 1 ? '' : 's'}.
                {createdCount === 1
                  ? ' Continue in the wizard to map columns once for all files in this batch.'
                  : ' Multiple layout groups — finish each job separately.'}
              </Alert>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Files</TableCell>
                    <TableCell>Job</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results.jobs.map((r) => (
                    <TableRow key={r.signature}>
                      <TableCell>{r.filenames.join(', ')}</TableCell>
                      <TableCell>{r.import_job_id != null ? `#${r.import_job_id}` : '—'}</TableCell>
                      <TableCell>
                        {r.outcome === 'created' ? (
                          <Chip size="small" color="success" label={r.stage ?? 'created'} />
                        ) : (
                          <Chip size="small" color="error" label={r.error ?? 'error'} />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={upload.isPending}>
          Close
        </Button>
        <Button
          variant="contained"
          disabled={!canUpload || upload.isPending || propose.isPending}
          onClick={() => void upload.mutateAsync()}
          startIcon={upload.isPending ? <CircularProgress size={16} /> : undefined}
          data-testid="dsi-bulk-upload-submit"
        >
          Upload batch
        </Button>
      </DialogActions>
    </Dialog>
  );
}

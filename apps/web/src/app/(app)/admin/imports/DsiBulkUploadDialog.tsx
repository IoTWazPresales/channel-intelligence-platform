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

type FileResult = {
  filename: string;
  import_job_id?: number;
  outcome: 'created' | 'error';
  error?: string;
  stage?: string | null;
};

export type DsiBulkUploadDialogProps = {
  open: boolean;
  onClose: () => void;
  sourceId: number | null;
  dsiWorkflowMode: 'auto' | 'historical' | 'weekly';
  onWorkflowModeChange: (mode: 'auto' | 'historical' | 'weekly') => void;
  /** Called with the first successfully created job id so the wizard can continue. */
  onJobsCreated: (jobIds: number[]) => void;
};

function extOk(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXT.some((e) => lower.endsWith(e));
}

/**
 * Multi-file DSI upload: one POST /imports/jobs per file (same contract as single upload).
 * Each file becomes its own import job with inline infer. Steward/mapping stays per-job.
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
  const [results, setResults] = useState<FileResult[] | null>(null);

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
    setResults(null);
  }, []);

  const removeAt = useCallback((idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setResults(null);
  }, []);

  const canSubmit = sourceId != null && files.length > 0;

  const upload = useMutation({
    mutationFn: async (): Promise<FileResult[]> => {
      if (sourceId == null) throw new Error('Select a DSI source first');
      const out: FileResult[] = [];
      for (const file of files) {
        const fd = new FormData();
        fd.append('source_id', String(sourceId));
        fd.append('file', file);
        fd.append('run_sync', 'false');
        fd.append('import_mode', 'validate');
        fd.append('dsi_workflow_mode', dsiWorkflowMode);
        try {
          const res = await fetch(apiUrl('/api/v1/imports/jobs'), {
            method: 'POST',
            headers: DEMO_HEADERS,
            body: fd,
          });
          if (!res.ok) {
            out.push({
              filename: file.name,
              outcome: 'error',
              error: await readFetchError(res),
            });
            continue;
          }
          const json = (await res.json()) as { id: number; stage?: string | null };
          out.push({
            filename: file.name,
            import_job_id: json.id,
            outcome: 'created',
            stage: json.stage ?? null,
          });
        } catch (e) {
          out.push({
            filename: file.name,
            outcome: 'error',
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
      return out;
    },
    onSuccess: (res) => {
      setResults(res);
      const ids = res
        .filter((r) => r.outcome === 'created' && r.import_job_id != null)
        .map((r) => r.import_job_id as number);
      if (ids.length) onJobsCreated(ids);
    },
  });

  const createdCount = useMemo(
    () => (results ?? []).filter((r) => r.outcome === 'created').length,
    [results]
  );

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="dsi-bulk-upload-dialog">
      <DialogTitle>DSI bulk upload (multi-file)</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Each file creates its own import job (same weekly/historical mode). Map and validate each job
            separately — multi-sheet workbooks are handled inside a single file.
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
              disabled={upload.isPending}
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
                        disabled={upload.isPending}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
          {upload.isPending ? <LinearProgress /> : null}
          {upload.isError ? <Alert severity="error">{safeDisplayError(upload.error)}</Alert> : null}
          {results ? (
            <Stack spacing={1} data-testid="dsi-bulk-results">
              <Alert severity={createdCount ? 'success' : 'warning'}>
                Created {createdCount} of {results.length} job(s). Open a job to map columns.
              </Alert>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>File</TableCell>
                    <TableCell>Job</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results.map((r) => (
                    <TableRow key={r.filename}>
                      <TableCell>{r.filename}</TableCell>
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
          disabled={!canSubmit || upload.isPending}
          onClick={() => void upload.mutateAsync()}
          startIcon={upload.isPending ? <CircularProgress size={16} /> : undefined}
          data-testid="dsi-bulk-upload-submit"
        >
          Upload {files.length || ''} file{files.length === 1 ? '' : 's'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

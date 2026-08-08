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
  IconButton,
  LinearProgress,
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
  '.csv,.xlsx,.xlsm,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,application/vnd.ms-excel,text/csv';

const ALLOWED_EXT = ['.csv', '.xlsx', '.xlsm', '.xls'];

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

export type CstBulkUploadDialogProps = {
  open: boolean;
  onClose: () => void;
  sourceId: number | null;
  /** First created batch job id — wizard continues with CST steward. */
  onJobsCreated: (jobIds: number[]) => void;
};

function extOk(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXT.some((e) => lower.endsWith(e));
}

/**
 * Unified multi-file CST upload: all CST-capable files → one import job
 * (per-file period from content, one steward pass). Unmappable files are skipped.
 */
export function CstBulkUploadDialog({
  open,
  onClose,
  sourceId,
  onJobsCreated,
}: CstBulkUploadDialogProps) {
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
      if (sourceId == null) throw new Error('Select a CST source first');
      const fd = new FormData();
      for (const file of files) {
        fd.append('files', file);
      }
      const res = await fetch(apiUrl('/api/v1/imports/cst/batch-propose'), {
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
      if (sourceId == null) throw new Error('Select a CST source first');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      for (const file of files) {
        fd.append('files', file);
      }
      const res = await fetch(apiUrl('/api/v1/imports/cst/batch-jobs'), {
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
      onClose();
    },
  });

  const createdCount = useMemo(
    () => (results?.jobs ?? []).filter((r) => r.outcome === 'created').length,
    [results]
  );

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="cst-bulk-upload-dialog">
      <DialogTitle>CST unified batch upload</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            All CST-capable files combine into <strong>one import job</strong> — period is taken from each
            file&apos;s content (e.g. Transaction Week), one steward pass, one apply. Unmappable files are
            skipped.
          </Typography>
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
            data-testid="cst-bulk-dropzone"
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
            <Table size="small" data-testid="cst-bulk-file-list">
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
              data-testid="cst-bulk-preview-groups"
            >
              Preview batch groups
            </Button>
          ) : null}
          {propose.isPending ? <LinearProgress /> : null}
          {propose.isError ? <Alert severity="error">{safeDisplayError(propose.error)}</Alert> : null}
          {preview ? (
            <Stack spacing={1} data-testid="cst-bulk-group-preview">
              <Alert severity="info">
                {preview.file_count} file{preview.file_count === 1 ? '' : 's'} →{' '}
                {preview.group_count} import job{preview.group_count === 1 ? '' : 's'}
                {preview.group_count === 1 ? ' (weeks can differ — periods come from file content)' : ''}
              </Alert>
              {preview.groups.map((g) => {
                const unmappableFiles = g.files.filter((f) => f.unmappable);
                const isCapable = g.signature === 'cst_capable';
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
                        ? `Skipped · not CST-mappable (${unmappableFiles.length})`
                        : isCapable
                          ? `One import job · ${g.files.length} file${g.files.length === 1 ? '' : 's'}`
                          : `Job group · ${g.signature}`}
                    </Typography>
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
            <Alert severity={createdCount ? 'success' : 'warning'} data-testid="cst-bulk-results">
              Created {createdCount} batch job{createdCount === 1 ? '' : 's'}. Continue to CST steward.
            </Alert>
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
          data-testid="cst-bulk-upload-submit"
        >
          Upload batch
        </Button>
      </DialogActions>
    </Dialog>
  );
}

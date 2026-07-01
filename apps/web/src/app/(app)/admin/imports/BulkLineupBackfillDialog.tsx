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
  FormControlLabel,
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
import { useMutation } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';
import { apiPostFormData, safeDisplayError } from '@/lib/api';

const ACCEPT =
  '.csv,.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,text/csv';

type CaseProposal = {
  proposal_key: string;
  filename: string;
  sheet_name: string;
  period_label: string | null;
  period_source_tier: string | null;
  period_flags: string[];
  business_unit: string | null;
  bu_report: {
    source_tier?: string | null;
    product_resolution_rate?: number | null;
    flags?: string[];
  };
  status: string;
  attention_reasons: string[];
  row_count: number;
  flags: string[];
};

type PreviewPayload = {
  session_import_job_id?: number;
  preview: {
    session_import_job_id?: number;
    case_proposals: CaseProposal[];
    supersession_collisions: Array<{
      supersession_group_key: string;
      winner_proposal_key: string;
      members: Array<{ proposal_key: string; filename: string; sheet_name: string }>;
    }>;
    catalogue_miss_worklist: Array<{ token: string; reference_count: number }>;
    totals: Record<string, number>;
  };
};

function statusChip(status: string) {
  if (status === 'ready') return <Chip size="small" color="success" label="Ready" />;
  if (status === 'needs_attention') return <Chip size="small" color="warning" label="Needs attention" />;
  return <Chip size="small" variant="outlined" label={status} />;
}

export type BulkLineupBackfillDialogProps = {
  open: boolean;
  onClose: () => void;
};

export function BulkLineupBackfillDialog({ open, onClose }: BulkLineupBackfillDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [folderPath, setFolderPath] = useState('');
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);

  const previewMutation = useMutation({
    mutationFn: async (selected: File[]) => {
      const fd = new FormData();
      selected.forEach((f) => fd.append('files', f));
      if (folderPath.trim()) {
        selected.forEach(() => fd.append('folder_paths', folderPath.trim()));
      }
      return apiPostFormData<PreviewPayload>('/api/v1/commercial-planner/lineup/bulk-backfill/preview', fd);
    },
    onSuccess: (data) => setPreview(data),
  });

  const applyMutation = useMutation({
    mutationFn: async (sessionId: number) => {
      const fd = new FormData();
      fd.append('session_import_job_id', String(sessionId));
      fd.append('confirm', 'true');
      const readyKeys =
        preview?.preview.case_proposals.filter((p) => p.status === 'ready').map((p) => p.proposal_key) ?? [];
      fd.append('approved_proposal_keys', JSON.stringify(readyKeys));
      return apiPostFormData<{ task_id?: string; session_import_job_id: number }>(
        '/api/v1/commercial-planner/lineup/bulk-backfill/apply',
        fd,
      );
    },
    onSuccess: (data) => {
      if (data.task_id) {
        registerClientBackgroundTask({
          taskId: data.task_id,
          kind: 'commercial_planner_lineup_parse',
          label: `Bulk lineup backfill (session ${data.session_import_job_id})`,
        });
      }
      onClose();
    },
  });

  const sessionId = preview?.session_import_job_id ?? preview?.preview?.session_import_job_id;

  const readyCount = useMemo(
    () => preview?.preview.case_proposals.filter((p) => p.status === 'ready').length ?? 0,
    [preview],
  );

  const onFiles = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    setPreview(null);
  }, []);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Bulk historical lineup backfill</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            File-grain steward preview: period + BU detection, sheet fan-out, supersession collisions, and
            catalogue-miss worklist. Nothing writes to lineup tables until you confirm apply.
          </Typography>

          <TextField
            label="Archive folder path (optional)"
            placeholder="NB\2025\Q1"
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            size="small"
            fullWidth
          />

          <Box
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              onFiles(e.dataTransfer.files);
            }}
            sx={{
              border: '1px dashed',
              borderColor: 'divider',
              borderRadius: 1,
              p: 2,
              textAlign: 'center',
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              multiple
              hidden
              onChange={(e) => onFiles(e.target.files)}
            />
            <Button startIcon={<CloudUploadOutlinedIcon />} onClick={() => inputRef.current?.click()}>
              Add lineup files
            </Button>
          </Box>

          {files.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {files.map((f, i) => (
                  <TableRow key={`${f.name}-${i}`}>
                    <TableCell>{f.name}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="inherit"
                        startIcon={<DeleteOutlineIcon />}
                        onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {previewMutation.isError && (
            <Alert severity="error">{safeDisplayError(previewMutation.error)}</Alert>
          )}
          {applyMutation.isError && <Alert severity="error">{safeDisplayError(applyMutation.error)}</Alert>}

          {preview && (
            <>
              <Alert severity="info">
                Preview session #{sessionId}: {preview.preview.totals?.files ?? files.length} files →{' '}
                {preview.preview.totals?.cases_ready ?? readyCount} ready cases,{' '}
                {preview.preview.totals?.cases_needs_attention ?? 0} needs attention,{' '}
                {preview.preview.totals?.collision_groups ?? 0} collision groups.
              </Alert>

              {preview.preview.supersession_collisions?.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Supersession collisions (latest-wins default)
                  </Typography>
                  {preview.preview.supersession_collisions.map((g) => (
                    <Typography key={g.supersession_group_key} variant="body2" sx={{ mb: 1 }}>
                      {g.supersession_group_key}: winner {g.winner_proposal_key} (
                      {g.members.map((m) => m.filename).join(', ')})
                    </Typography>
                  ))}
                </Box>
              )}

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>File / sheet</TableCell>
                    <TableCell>Period</TableCell>
                    <TableCell>BU</TableCell>
                    <TableCell>Rows</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.preview.case_proposals.map((p) => (
                    <TableRow key={p.proposal_key}>
                      <TableCell>
                        {p.filename}
                        {p.sheet_name ? ` / ${p.sheet_name}` : ''}
                      </TableCell>
                      <TableCell>
                        {p.period_label ?? '—'}
                        {p.period_source_tier ? ` (${p.period_source_tier})` : ''}
                      </TableCell>
                      <TableCell>
                        {p.business_unit ?? '—'}
                        {p.bu_report?.source_tier ? ` (${p.bu_report.source_tier})` : ''}
                        {(p.bu_report?.flags ?? p.flags).map((f) => (
                          <Chip key={f} size="small" label={f} sx={{ ml: 0.5, mt: 0.5 }} />
                        ))}
                      </TableCell>
                      <TableCell>{p.row_count}</TableCell>
                      <TableCell>{statusChip(p.status)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {preview.preview.catalogue_miss_worklist?.length > 0 && (
                <Box>
                  <Typography variant="subtitle2">Referenced but not in catalogue (advisory)</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {preview.preview.catalogue_miss_worklist
                      .slice(0, 8)
                      .map((w) => w.token)
                      .join(', ')}
                    {preview.preview.catalogue_miss_worklist.length > 8 ? '…' : ''}
                  </Typography>
                </Box>
              )}

              <FormControlLabel
                control={<Switch checked={confirmApply} onChange={(e) => setConfirmApply(e.target.checked)} />}
                label="I have reviewed the preview and approve applying ready cases only"
              />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="outlined"
          disabled={!files.length || previewMutation.isPending}
          onClick={() => previewMutation.mutate(files)}
        >
          {previewMutation.isPending ? <CircularProgress size={20} /> : 'Run preview'}
        </Button>
        <Button
          variant="contained"
          disabled={!sessionId || !confirmApply || readyCount === 0 || applyMutation.isPending}
          onClick={() => sessionId && applyMutation.mutate(sessionId)}
        >
          {applyMutation.isPending ? <CircularProgress size={20} /> : `Apply ${readyCount} cases`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

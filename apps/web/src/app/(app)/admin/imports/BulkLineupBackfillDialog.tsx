'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
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
  FormControlLabel,
  Radio,
  RadioGroup,
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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';
import { apiPostFormData, safeDisplayError } from '@/lib/api';

const ACCEPT =
  '.csv,.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,text/csv';

const TENANT_BU_OPTIONS = ['NB', 'NR', 'NV', 'NX', 'PF', 'XB'] as const;

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

type CollisionGroup = {
  supersession_group_key: string;
  winner_proposal_key: string;
  period_label?: string | null;
  customer_token?: string | null;
  business_unit?: string | null;
  members: Array<{ proposal_key: string; filename: string; sheet_name: string; row_count?: number }>;
};

type PreviewPayload = {
  session_import_job_id?: number | null;
  persisted?: boolean;
  preview: {
    session_import_job_id?: number;
    case_proposals: CaseProposal[];
    supersession_collisions: CollisionGroup[];
    catalogue_miss_worklist: Array<{ token: string; reference_count: number }>;
    totals: Record<string, number>;
  };
};

type StewardOverrides = Record<string, { period_label?: string; business_unit?: string }>;

function statusChip(status: string) {
  if (status === 'ready') return <Chip size="small" color="success" label="Ready" />;
  if (status === 'needs_attention') return <Chip size="small" color="warning" label="Needs attention" />;
  return <Chip size="small" variant="outlined" label={status} />;
}

function buildManualOverrides(
  periodOverrides: Record<string, string>,
  buOverrides: Record<string, string>,
  proposals: CaseProposal[],
): StewardOverrides | undefined {
  const out: StewardOverrides = {};
  for (const p of proposals) {
    const period = periodOverrides[p.proposal_key]?.trim();
    const bu = buOverrides[p.proposal_key]?.trim();
    const periodChanged = period && period !== (p.period_label ?? '');
    const buChanged = bu && bu.toUpperCase() !== (p.business_unit ?? '').toUpperCase();
    if (periodChanged || buChanged) {
      out[p.proposal_key] = {};
      if (periodChanged) out[p.proposal_key].period_label = period;
      if (buChanged) out[p.proposal_key].business_unit = bu.toUpperCase();
    }
  }
  return Object.keys(out).length ? out : undefined;
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
  const [periodOverrides, setPeriodOverrides] = useState<Record<string, string>>({});
  const [buOverrides, setBuOverrides] = useState<Record<string, string>>({});
  const [collisionWinners, setCollisionWinners] = useState<Record<string, string>>({});

  const syncOverrideFields = useCallback((data: PreviewPayload) => {
    const periods: Record<string, string> = {};
    const bus: Record<string, string> = {};
    for (const p of data.preview.case_proposals) {
      periods[p.proposal_key] = p.period_label ?? '';
      bus[p.proposal_key] = p.business_unit ?? '';
    }
    setPeriodOverrides(periods);
    setBuOverrides(bus);

    const winners: Record<string, string> = {};
    for (const g of data.preview.supersession_collisions ?? []) {
      winners[g.supersession_group_key] = g.winner_proposal_key;
    }
    setCollisionWinners(winners);
  }, []);

  const runPreview = useCallback(
    async (selected: File[], overrides?: StewardOverrides) => {
      const fd = new FormData();
      selected.forEach((f) => fd.append('files', f));
      if (folderPath.trim()) {
        selected.forEach(() => fd.append('folder_paths', folderPath.trim()));
      }
      if (overrides && Object.keys(overrides).length) {
        fd.append('manual_overrides', JSON.stringify(overrides));
      }
      return apiPostFormData<PreviewPayload>('/api/v1/commercial-planner/lineup/bulk-backfill/preview', fd);
    },
    [folderPath],
  );

  const previewMutation = useMutation({
    mutationFn: (selected: File[]) => runPreview(selected),
    onSuccess: (data) => {
      setPreview(data);
      syncOverrideFields(data);
    },
  });

  const rerunWithOverridesMutation = useMutation({
    mutationFn: (selected: File[]) => {
      const overrides = buildManualOverrides(
        periodOverrides,
        buOverrides,
        preview?.preview.case_proposals ?? [],
      );
      return runPreview(selected, overrides);
    },
    onSuccess: (data) => {
      setPreview(data);
      syncOverrideFields(data);
    },
  });

  const applyMutation = useMutation({
    mutationFn: async (sessionId: number) => {
      const proposals = preview?.preview.case_proposals ?? [];
      const collisions = preview?.preview.supersession_collisions ?? [];
      const readyKeys = proposals.filter((p) => p.status === 'ready').map((p) => p.proposal_key);

      const supersessionConfirmations: Record<string, string> = {};
      for (const g of collisions) {
        const chosen = collisionWinners[g.supersession_group_key] ?? g.winner_proposal_key;
        supersessionConfirmations[g.supersession_group_key] = chosen;
      }

      const fd = new FormData();
      fd.append('session_import_job_id', String(sessionId));
      fd.append('confirm', 'true');
      fd.append('approved_proposal_keys', JSON.stringify(readyKeys));
      if (Object.keys(supersessionConfirmations).length) {
        fd.append('supersession_confirmations', JSON.stringify(supersessionConfirmations));
      }
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

  const hasPendingOverrides = useMemo(() => {
    if (!preview) return false;
    return Boolean(
      buildManualOverrides(periodOverrides, buOverrides, preview.preview.case_proposals),
    );
  }, [preview, periodOverrides, buOverrides]);

  const collisionMemberKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const g of preview?.preview.supersession_collisions ?? []) {
      for (const m of g.members) keys.add(m.proposal_key);
    }
    return keys;
  }, [preview]);

  const onFiles = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    setPreview(null);
    setPeriodOverrides({});
    setBuOverrides({});
    setCollisionWinners({});
  }, []);

  useEffect(() => {
    if (!open) {
      setConfirmApply(false);
    }
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Bulk historical lineup backfill</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            File-grain steward preview: edit period/BU overrides per case, pick collision winners,
            then re-run preview before apply. Nothing writes to lineup tables until you confirm apply.
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
          {rerunWithOverridesMutation.isError && (
            <Alert severity="error">{safeDisplayError(rerunWithOverridesMutation.error)}</Alert>
          )}
          {applyMutation.isError && <Alert severity="error">{safeDisplayError(applyMutation.error)}</Alert>}

          {preview && (
            <>
              <Alert severity="info">
                Preview session #{sessionId ?? 'in-memory'}: {preview.preview.totals?.files ?? files.length}{' '}
                files → {preview.preview.totals?.cases_ready ?? readyCount} ready cases,{' '}
                {preview.preview.totals?.cases_needs_attention ?? 0} needs attention,{' '}
                {preview.preview.totals?.collision_groups ?? 0} collision groups.
                {hasPendingOverrides && ' — steward overrides pending re-preview.'}
              </Alert>

              {preview.preview.supersession_collisions?.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Supersession collisions — pick winner (default: latest file)
                  </Typography>
                  {preview.preview.supersession_collisions.map((g) => (
                    <Box
                      key={g.supersession_group_key}
                      sx={{ mb: 2, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
                    >
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        {g.supersession_group_key}
                        {g.period_label ? ` · ${g.period_label}` : ''}
                        {g.business_unit ? ` · ${g.business_unit}` : ''}
                      </Typography>
                      <FormControl component="fieldset" size="small">
                        <RadioGroup
                          value={collisionWinners[g.supersession_group_key] ?? g.winner_proposal_key}
                          onChange={(e) =>
                            setCollisionWinners((prev) => ({
                              ...prev,
                              [g.supersession_group_key]: e.target.value,
                            }))
                          }
                        >
                          {g.members.map((m) => (
                            <FormControlLabel
                              key={m.proposal_key}
                              value={m.proposal_key}
                              control={<Radio size="small" />}
                              label={`${m.filename}${m.sheet_name ? ` / ${m.sheet_name}` : ''}${
                                m.proposal_key === g.winner_proposal_key ? ' (default)' : ''
                              }`}
                            />
                          ))}
                        </RadioGroup>
                      </FormControl>
                    </Box>
                  ))}
                </Box>
              )}

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>File / sheet</TableCell>
                    <TableCell>Period (override)</TableCell>
                    <TableCell>BU (override)</TableCell>
                    <TableCell>Rows</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.preview.case_proposals.map((p) => {
                    const inCollision = collisionMemberKeys.has(p.proposal_key);
                    return (
                      <TableRow
                        key={p.proposal_key}
                        sx={inCollision ? { bgcolor: 'action.hover' } : undefined}
                      >
                        <TableCell>
                          {p.filename}
                          {p.sheet_name ? ` / ${p.sheet_name}` : ''}
                          {inCollision && (
                            <Chip size="small" label="collision" sx={{ ml: 1 }} color="info" />
                          )}
                        </TableCell>
                        <TableCell>
                          <TextField
                            size="small"
                            value={periodOverrides[p.proposal_key] ?? p.period_label ?? ''}
                            onChange={(e) =>
                              setPeriodOverrides((prev) => ({
                                ...prev,
                                [p.proposal_key]: e.target.value,
                              }))
                            }
                            placeholder={p.period_label ?? 'e.g. Q1 2025'}
                            helperText={
                              p.period_source_tier && !periodOverrides[p.proposal_key]
                                ? `detected (${p.period_source_tier})`
                                : undefined
                            }
                            FormHelperTextProps={{ sx: { m: 0 } }}
                            sx={{ minWidth: 140 }}
                          />
                          {(p.period_flags ?? []).map((f) => (
                            <Chip key={f} size="small" label={f} sx={{ ml: 0.5, mt: 0.5 }} />
                          ))}
                        </TableCell>
                        <TableCell>
                          <TextField
                            size="small"
                            select
                            SelectProps={{ native: true }}
                            value={(buOverrides[p.proposal_key] ?? p.business_unit ?? '').toUpperCase()}
                            onChange={(e) =>
                              setBuOverrides((prev) => ({
                                ...prev,
                                [p.proposal_key]: e.target.value,
                              }))
                            }
                            sx={{ minWidth: 88 }}
                          >
                            <option value="">—</option>
                            {TENANT_BU_OPTIONS.map((bu) => (
                              <option key={bu} value={bu}>
                                {bu}
                              </option>
                            ))}
                          </TextField>
                          {(p.bu_report?.flags ?? p.flags).map((f) => (
                            <Chip key={f} size="small" label={f} sx={{ ml: 0.5, mt: 0.5 }} />
                          ))}
                        </TableCell>
                        <TableCell>{p.row_count}</TableCell>
                        <TableCell>{statusChip(p.status)}</TableCell>
                      </TableRow>
                    );
                  })}
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
          variant="outlined"
          color="secondary"
          disabled={!preview || !files.length || rerunWithOverridesMutation.isPending || !hasPendingOverrides}
          startIcon={
            rerunWithOverridesMutation.isPending ? (
              <CircularProgress size={16} />
            ) : (
              <RefreshOutlinedIcon />
            )
          }
          onClick={() => rerunWithOverridesMutation.mutate(files)}
        >
          Re-run with overrides
        </Button>
        <Button
          variant="contained"
          disabled={
            !sessionId ||
            !confirmApply ||
            readyCount === 0 ||
            applyMutation.isPending ||
            hasPendingOverrides
          }
          onClick={() => sessionId && applyMutation.mutate(sessionId)}
        >
          {applyMutation.isPending ? <CircularProgress size={20} /> : `Apply ${readyCount} cases`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

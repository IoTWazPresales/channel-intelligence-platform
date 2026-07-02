'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import FolderOpenOutlinedIcon from '@mui/icons-material/FolderOpenOutlined';
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

import {
  mergeStagedLineupFiles,
  type StagedLineupFile,
  stageLineupFilesFromList,
} from '@/features/commercial-planner/lineupBackfillArchivePath';
import {
  buildAutoBaseline,
  buildCumulativeStewardPayload,
  displayFieldsFromPreview,
  hasPendingStewardDeltas,
  mergeCollisionWinners,
  type AutoBaseline,
  type StewardOverrides,
} from '@/features/commercial-planner/lineupBackfillStewardOverrides';
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

function statusChip(status: string) {
  if (status === 'ready') return <Chip size="small" color="success" label="Ready" />;
  if (status === 'needs_attention') return <Chip size="small" color="warning" label="Needs attention" />;
  return <Chip size="small" variant="outlined" label={status} />;
}

function appendFolderPaths(fd: FormData, staged: StagedLineupFile[], globalFolderOverride: string) {
  const globalOverride = globalFolderOverride.trim();
  staged.forEach((s) => {
    fd.append('files', s.file);
    const folderPath = globalOverride || s.folderPath || '';
    fd.append('folder_paths', folderPath);
  });
}

export type BulkLineupBackfillDialogProps = {
  open: boolean;
  onClose: () => void;
};

export function BulkLineupBackfillDialog({ open, onClose }: BulkLineupBackfillDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [stagedFiles, setStagedFiles] = useState<StagedLineupFile[]>([]);
  const [folderPathOverride, setFolderPathOverride] = useState('');
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [periodOverrides, setPeriodOverrides] = useState<Record<string, string>>({});
  const [buOverrides, setBuOverrides] = useState<Record<string, string>>({});
  const [autoBaseline, setAutoBaseline] = useState<AutoBaseline>({});
  const [collisionWinners, setCollisionWinners] = useState<Record<string, string>>({});
  const [loadNotice, setLoadNotice] = useState<string | null>(null);

  const resetPreviewState = useCallback(() => {
    setPreview(null);
    setPeriodOverrides({});
    setBuOverrides({});
    setAutoBaseline({});
    setCollisionWinners({});
    setConfirmApply(false);
  }, []);

  const syncAfterFreshPreview = useCallback((data: PreviewPayload) => {
    const proposals = data.preview.case_proposals;
    setAutoBaseline(buildAutoBaseline(proposals));
    const periods: Record<string, string> = {};
    const bus: Record<string, string> = {};
    for (const p of proposals) {
      periods[p.proposal_key] = p.period_label ?? '';
      bus[p.proposal_key] = p.business_unit ?? '';
    }
    setPeriodOverrides(periods);
    setBuOverrides(bus);
    setCollisionWinners(mergeCollisionWinners(data.preview.supersession_collisions ?? [], {}));
  }, []);

  const syncAfterRerunPreview = useCallback((data: PreviewPayload, cumulativePayload: StewardOverrides) => {
    const proposals = data.preview.case_proposals;
    const display = displayFieldsFromPreview(proposals, cumulativePayload);
    setPeriodOverrides(display.periodOverrides);
    setBuOverrides(display.buOverrides);
    setCollisionWinners((prev) =>
      mergeCollisionWinners(data.preview.supersession_collisions ?? [], prev),
    );
  }, []);

  const runPreview = useCallback(
    async (staged: StagedLineupFile[], overrides?: StewardOverrides) => {
      const fd = new FormData();
      appendFolderPaths(fd, staged, folderPathOverride);
      if (overrides && Object.keys(overrides).length) {
        fd.append('manual_overrides', JSON.stringify(overrides));
      }
      return apiPostFormData<PreviewPayload>('/api/v1/commercial-planner/lineup/bulk-backfill/preview', fd);
    },
    [folderPathOverride],
  );

  const previewMutation = useMutation({
    mutationFn: (staged: StagedLineupFile[]) => runPreview(staged),
    onSuccess: (data) => {
      setPreview(data);
      syncAfterFreshPreview(data);
    },
  });

  const rerunWithOverridesMutation = useMutation({
    mutationFn: async (staged: StagedLineupFile[]) => {
      const proposals = preview?.preview.case_proposals ?? [];
      const cumulativePayload = buildCumulativeStewardPayload(
        proposals,
        periodOverrides,
        buOverrides,
        autoBaseline,
      );
      const data = await runPreview(
        staged,
        Object.keys(cumulativePayload).length ? cumulativePayload : undefined,
      );
      return { data, cumulativePayload };
    },
    onSuccess: ({ data, cumulativePayload }) => {
      setPreview(data);
      syncAfterRerunPreview(data, cumulativePayload);
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
    return hasPendingStewardDeltas(
      preview.preview.case_proposals,
      periodOverrides,
      buOverrides,
    );
  }, [preview, periodOverrides, buOverrides]);

  const collisionMemberKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const g of preview?.preview.supersession_collisions ?? []) {
      for (const m of g.members) keys.add(m.proposal_key);
    }
    return keys;
  }, [preview]);

  const onAddFiles = useCallback(
    (list: FileList | null) => {
      if (!list?.length) return;
      const incoming = stageLineupFilesFromList(list);
      if (!incoming.length) {
        setLoadNotice('No lineup spreadsheets found in selection (need .xlsx / .xlsm / .csv).');
        return;
      }
      setStagedFiles((prev) => mergeStagedLineupFiles(prev, incoming, 'append'));
      setLoadNotice(`Added ${incoming.length} file(s).`);
      resetPreviewState();
    },
    [resetPreviewState],
  );

  const onSelectArchiveFolder = useCallback(
    (list: FileList | null) => {
      if (!list?.length) return;
      const incoming = stageLineupFilesFromList(list);
      if (!incoming.length) {
        setLoadNotice('No lineup spreadsheets found under that folder.');
        return;
      }
      setStagedFiles((prev) => mergeStagedLineupFiles(prev, incoming, 'replace'));
      const withPaths = incoming.filter((s) => s.folderPath).length;
      setLoadNotice(
        `Loaded ${incoming.length} lineup file(s) from archive tree (${withPaths} with NB/NR/…/year/quarter paths).`,
      );
      resetPreviewState();
    },
    [resetPreviewState],
  );

  useEffect(() => {
    if (!open) {
      setConfirmApply(false);
      setLoadNotice(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Bulk historical lineup backfill</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Select your <strong>Product Lineup</strong> root once — all NB/NR/NV/PF/XB subfolders are
            included. Period/BU paths are inferred from each file&apos;s place in the tree. Edit overrides
            after preview; nothing writes until you confirm apply.
          </Typography>

          <Box
            sx={{
              border: '1px dashed',
              borderColor: 'divider',
              borderRadius: 1,
              p: 2,
              textAlign: 'center',
            }}
          >
            <input
              ref={folderInputRef}
              type="file"
              // @ts-expect-error webkitdirectory is supported in Chromium/Edge folder picker
              webkitdirectory=""
              directory=""
              multiple
              hidden
              onChange={(e) => {
                onSelectArchiveFolder(e.target.files);
                e.target.value = '';
              }}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              multiple
              hidden
              onChange={(e) => {
                onAddFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="center">
              <Button
                variant="contained"
                startIcon={<FolderOpenOutlinedIcon />}
                onClick={() => folderInputRef.current?.click()}
              >
                Select archive folder
              </Button>
              <Button
                variant="outlined"
                startIcon={<CloudUploadOutlinedIcon />}
                onClick={() => fileInputRef.current?.click()}
              >
                Add individual files
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              Use <em>Select archive folder</em> on Product Lineup (or any parent) — not per-BU file picking.
            </Typography>
          </Box>

          {loadNotice && (
            <Alert severity="info" onClose={() => setLoadNotice(null)}>
              {loadNotice}
            </Alert>
          )}

          <TextField
            label="Override folder path for all files (optional)"
            placeholder="NB\2025\Q1 — only if not using archive folder picker"
            value={folderPathOverride}
            onChange={(e) => setFolderPathOverride(e.target.value)}
            size="small"
            fullWidth
          />

          {stagedFiles.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell>Inferred path</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stagedFiles.map((s, i) => (
                  <TableRow key={`${s.relativePath}-${i}`}>
                    <TableCell title={s.relativePath}>{s.file.name}</TableCell>
                    <TableCell>{s.folderPath ?? '—'}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="inherit"
                        startIcon={<DeleteOutlineIcon />}
                        onClick={() => {
                          setStagedFiles((prev) => prev.filter((_, j) => j !== i));
                          resetPreviewState();
                        }}
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
                Preview session #{sessionId ?? 'in-memory'}: {preview.preview.totals?.files ?? stagedFiles.length}{' '}
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
          disabled={!stagedFiles.length || previewMutation.isPending}
          onClick={() => previewMutation.mutate(stagedFiles)}
        >
          {previewMutation.isPending ? <CircularProgress size={20} /> : 'Run preview'}
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          disabled={
            !preview || !stagedFiles.length || rerunWithOverridesMutation.isPending || !hasPendingOverrides
          }
          startIcon={
            rerunWithOverridesMutation.isPending ? (
              <CircularProgress size={16} />
            ) : (
              <RefreshOutlinedIcon />
            )
          }
          onClick={() => rerunWithOverridesMutation.mutate(stagedFiles)}
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

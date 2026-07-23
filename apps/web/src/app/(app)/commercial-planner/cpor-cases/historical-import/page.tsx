'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';
import { useImportJobProgressQuery } from '@/features/background-tasks/useImportJobProgressQuery';
import { CanonicalColumnMappingPanel } from '@/features/import-mapping/CanonicalColumnMappingPanel';
import { apiGet, apiPostFormData, safeDisplayError } from '@/lib/api';
import { ImportJobValidateProgressPanel } from '@/features/import-steward/ImportJobValidateProgressPanel';

import { CporHistoricalImportJobResolutionSection } from './CporHistoricalImportJobResolutionSection';
import {
  applyCporHistoricalJob,
  fetchCporHistoricalSummary,
  validateCporHistoricalJob,
} from './cporHistoricalImportApi';
import {
  CPOR_HISTORICAL_STEWARD_CONFIG,
  invalidateCporHistoricalStewardQueries,
} from './cporHistoricalSteward.config';

type Source = { id: number; code: string; name: string; import_template_slug?: string | null };
type Profile = {
  id: number;
  profile_code: string;
  display_name: string;
  column_map_json: Record<string, string[]>;
  sheet_roles_json: Record<string, string>;
  is_default: boolean;
};

type WizardStep = 'upload' | 'validate' | 'resolve' | 'apply';

const STEP_LABELS: { id: WizardStep; label: string }[] = [
  { id: 'upload', label: 'Upload & profile' },
  { id: 'validate', label: 'Validate' },
  { id: 'resolve', label: 'Resolve entities' },
  { id: 'apply', label: 'Apply' },
];

const CPOR_PROGRESS_PHASES = [
  { id: 'queued', label: 'Queued' },
  { id: 'processing_rows', label: 'Validate / stage' },
  { id: 'applying_cases', label: 'Apply cases' },
  { id: 'complete', label: 'Complete' },
] as const;

export default function CporHistoricalImportPage() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [step, setStep] = useState<WizardStep>('upload');
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pollProgress, setPollProgress] = useState(false);
  const [applyConfirmOpen, setApplyConfirmOpen] = useState(false);

  const { data: sources } = useQuery({
    queryKey: ['imports', 'sources', 'cpor_historical_cases'],
    queryFn: ({ signal }) =>
      apiGet<Source[]>(`/api/v1/imports/sources?template_slug=cpor_historical_cases`, { signal }),
  });
  const sourceId = sources?.[0]?.id ?? null;

  const { data: profiles } = useQuery({
    queryKey: ['cpor', 'historical', 'profiles'],
    queryFn: ({ signal }) =>
      apiGet<{ profiles: Profile[] }>('/api/v1/cpor/historical-import/profiles', {
        signal,
        headers: { 'X-User-Role': 'admin' },
      }),
  });
  const profile = profiles?.profiles?.find((p) => p.is_default) ?? profiles?.profiles?.[0];

  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(jobId ?? 0),
    enabled: jobId != null,
    queryFn: ({ signal }) => fetchCporHistoricalSummary(jobId!, signal),
  });

  const { data: progress } = useImportJobProgressQuery(jobId, {
    enabled: pollProgress && jobId != null,
    kind: 'cpor_historical_import',
  });

  const progressPhase = String(progress?.phase ?? '').trim();
  const progressTerminal =
    progressPhase === 'complete' ||
    progressPhase === 'failed' ||
    progressPhase === 'loaded';

  useEffect(() => {
    if (!pollProgress || !progressTerminal) return;
    setPipelineRunning(false);
    setPollProgress(false);
    if (jobId != null) {
      invalidateCporHistoricalStewardQueries(qc, jobId);
      void refetchSummary();
    }
    if (progressPhase === 'failed') return;
    if (step === 'validate') {
      setStep('resolve');
    }
  }, [pollProgress, progressTerminal, progressPhase, jobId, qc, refetchSummary, step]);

  const targetOptions = useMemo(() => {
    if (!profile) return [];
    return Object.keys(profile.column_map_json || {}).map((k) => ({
      value: k,
      label: k,
    }));
  }, [profile]);

  const mappingDraft = useMemo(() => {
    const draft: Record<string, string> = {};
    if (!profile) return draft;
    for (const [canon, aliases] of Object.entries(profile.column_map_json || {})) {
      const header = aliases?.[0];
      if (header) draft[header] = canon;
    }
    return draft;
  }, [profile]);

  const startPipelinePoll = useCallback(
    (args: { importJobId: number; taskId?: string | null; label: string }) => {
      setPipelineRunning(true);
      setPollProgress(true);
      if (args.taskId) {
        registerClientBackgroundTask({
          taskId: args.taskId,
          importJobId: args.importJobId,
          kind: 'cpor_historical_import',
          label: args.label,
        });
      }
    },
    []
  );

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || sourceId == null) throw new Error('Pick a workbook and ensure source exists');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      fd.append('file', file);
      fd.append('run_sync', 'false');
      fd.append('import_mode', 'validate');
      return apiPostFormData<{ id: number; stage: string; status: string }>('/api/v1/imports/jobs', fd);
    },
    onSuccess: async (res) => {
      setJobId(res.id);
      setStep('validate');
      try {
        const validateRes = await validateCporHistoricalJob(res.id);
        startPipelinePoll({
          importJobId: res.id,
          taskId: validateRes.task_id,
          label: `CPOR historical validate #${res.id}`,
        });
        if (!validateRes.async) {
          setPipelineRunning(false);
          setPollProgress(false);
          invalidateCporHistoricalStewardQueries(qc, res.id);
          setStep('resolve');
        }
      } catch (e) {
        setPipelineRunning(false);
        setPollProgress(false);
        throw e;
      }
    },
  });

  const apply = useMutation({
    mutationFn: async () => {
      if (jobId == null) throw new Error('No import job');
      return applyCporHistoricalJob(jobId);
    },
    onSuccess: (res) => {
      setApplyConfirmOpen(false);
      setStep('apply');
      startPipelinePoll({
        importJobId: jobId!,
        taskId: res.task_id,
        label: `CPOR historical apply #${jobId}`,
      });
      if (!res.async) {
        setPipelineRunning(false);
        setPollProgress(false);
        void refetchSummary();
      }
    },
  });

  const canOpenResolve =
    jobId != null &&
    (summary?.stage === 'validated' ||
      summary?.stage === 'loaded' ||
      step === 'resolve' ||
      step === 'apply');

  const stepIndex = STEP_LABELS.findIndex((s) => s.id === step);

  return (
    <>
      <PageHeader
        crumbs={[
          { label: 'Commercial Planning' },
          { label: 'CPOR Cases', href: '/commercial-planner/cpor-cases' },
          { label: 'Historical import' },
        ]}
        title="CPOR historical import"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Upload an ASUS-style tracking workbook. Settled Results are stored as a frozen snapshot (parity
        flags only). Unresolved entities block that case only — never auto-create masters. Column mapping
        is driven by the seeded profile; steward mapping resolves products, customers, and distributors.
      </Alert>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        {STEP_LABELS.map((s, i) => (
          <Chip
            key={s.id}
            label={`${i + 1}. ${s.label}`}
            color={step === s.id ? 'primary' : 'default'}
            variant={step === s.id ? 'filled' : 'outlined'}
            onClick={() => {
              if (s.id === 'upload') setStep('upload');
              else if (s.id === 'validate' && jobId != null) setStep('validate');
              else if (s.id === 'resolve' && canOpenResolve) setStep('resolve');
              else if (s.id === 'apply' && jobId != null && (summary?.cases_ready ?? 0) >= 0) {
                setStep('apply');
              }
            }}
            data-testid={`cpor-historical-step-${s.id}`}
          />
        ))}
      </Stack>

      {step === 'upload' ? (
        <Stack spacing={2}>
          {!sourceId ? (
            <Alert severity="warning">
              No active source for <code>cpor_historical_cases</code>. Ensure default sources are seeded.
            </Alert>
          ) : null}
          {profile ? (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Mapping profile: {profile.display_name} ({profile.profile_code})
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Profile-driven column map (read-only). The resolve step maps unresolved entity tokens to
                masters — that is the steward work, not re-mapping headers here.
              </Typography>
              <CanonicalColumnMappingPanel
                fileHeaders={Object.values(profile.column_map_json || {}).flat()}
                draft={mappingDraft}
                onChange={() => undefined}
                targetOptions={targetOptions}
                disabled
                testIdPrefix="cpor-historical"
              />
            </Box>
          ) : (
            <Alert severity="info">Loading mapping profiles…</Alert>
          )}
          <Button variant="outlined" component="label" data-testid="cpor-historical-file">
            {file ? file.name : 'Choose .xlsx workbook'}
            <input
              hidden
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          <Button
            variant="contained"
            disabled={!file || sourceId == null || upload.isPending}
            onClick={() => upload.mutate()}
            data-testid="cpor-historical-upload"
          >
            {upload.isPending ? 'Uploading…' : 'Upload & validate'}
          </Button>
          {upload.isError ? <Alert severity="error">{safeDisplayError(upload.error)}</Alert> : null}
        </Stack>
      ) : null}

      {(step === 'validate' || (pollProgress && stepIndex <= 1)) && jobId != null ? (
        <Stack spacing={2} sx={{ mb: 2 }}>
          <ImportJobValidateProgressPanel
            progress={progress}
            isRunning={pipelineRunning && step === 'validate'}
            title="CPOR historical validation"
            phases={CPOR_PROGRESS_PHASES}
            phaseDescriptions={{
              queued: 'Waiting for a worker to pick up validate.',
              processing_rows: 'Parsing workbook, staging lines, and running deterministic resolve.',
              applying_cases: 'Apply is in progress (see Apply step).',
              complete: 'Validation finished — continue to resolve unresolved tokens.',
            }}
          />
          {progressPhase === 'failed' ? (
            <Alert severity="error">
              Validation failed{progress?.status ? ` (${progress.status})` : ''}. Check the job error
              summary and retry upload.
            </Alert>
          ) : null}
          {summary && !pipelineRunning && summary.stage === 'validated' ? (
            <Alert severity="success">
              Job {summary.id} validated · {summary.staging_count} staging rows ·{' '}
              {summary.cases_ready} ready · {summary.cases_blocked} blocked
            </Alert>
          ) : null}
          {!pipelineRunning && summary?.stage === 'validated' ? (
            <Button variant="contained" onClick={() => setStep('resolve')} data-testid="cpor-historical-continue-resolve">
              Continue to resolve
            </Button>
          ) : null}
        </Stack>
      ) : null}

      {(step === 'resolve' || step === 'apply') && jobId != null ? (
        <Stack spacing={2}>
          <CporHistoricalImportJobResolutionSection
            importJobId={jobId}
            pipelineRunning={pipelineRunning}
            onInvalidate={() => {
              void refetchSummary();
            }}
            onAsyncPipelineStarted={({ importJobId, taskId }) => {
              if (taskId) {
                startPipelinePoll({
                  importJobId,
                  taskId,
                  label: `CPOR historical job #${importJobId}`,
                });
              } else {
                void refetchSummary();
              }
            }}
          />

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            <Button variant="outlined" onClick={() => setStep('upload')} disabled={pipelineRunning}>
              Back to upload
            </Button>
            {!applyConfirmOpen ? (
              <Button
                variant="contained"
                color="warning"
                disabled={
                  apply.isPending ||
                  pipelineRunning ||
                  (summary?.cases_ready ?? 0) < 1 ||
                  (summary?.stage !== 'validated' && summary?.stage !== 'loaded')
                }
                onClick={() => setApplyConfirmOpen(true)}
                data-testid="cpor-historical-apply"
              >
                Apply {summary?.cases_ready ?? 0} ready case(s)
              </Button>
            ) : (
              <>
                <Alert severity="warning" sx={{ flex: 1 }}>
                  Apply {summary?.cases_ready ?? 0} ready case(s) with origin=historical_import? Blocked
                  cases stay staged.
                </Alert>
                <Button variant="outlined" onClick={() => setApplyConfirmOpen(false)} disabled={apply.isPending}>
                  Cancel
                </Button>
                <Button
                  variant="contained"
                  color="warning"
                  disabled={apply.isPending}
                  onClick={() => apply.mutate()}
                  data-testid="cpor-historical-apply-confirm"
                >
                  {apply.isPending ? 'Queuing…' : 'Confirm apply'}
                </Button>
              </>
            )}
            <Button component={Link} href="/commercial-planner/cpor-cases" variant="text">
              Back to cases
            </Button>
          </Stack>
          {apply.isError ? <Alert severity="error">{safeDisplayError(apply.error)}</Alert> : null}
        </Stack>
      ) : null}

      {(step === 'apply' || (pollProgress && step === 'apply')) && jobId != null ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <ImportJobValidateProgressPanel
            progress={progress}
            isRunning={pipelineRunning}
            title="CPOR historical apply"
            phases={CPOR_PROGRESS_PHASES}
            phaseDescriptions={{
              queued: 'Apply queued for a worker.',
              processing_rows: 'Preparing apply.',
              applying_cases: 'Upserting ready cases and lines.',
              complete: 'Apply finished.',
            }}
          />
          {summary && !pipelineRunning ? (
            <Alert severity="info" data-testid="cpor-historical-apply-done">
              Apply finished with status <strong>{summary.status}</strong>. Ready cases land with{' '}
              <code>origin=historical_import</code>. Blocked cases stay staged for further mapping.
              {summary.cpor_historical && typeof summary.cpor_historical === 'object' && 'apply' in summary.cpor_historical
                ? ` Applied ${(summary.cpor_historical.apply as { applied_cases?: number })?.applied_cases ?? '—'}; blocked ${(summary.cpor_historical.apply as { blocked_cases?: number })?.blocked_cases ?? '—'}.`
                : null}
            </Alert>
          ) : null}
        </Stack>
      ) : null}
    </>
  );
}

'use client';

import { Alert, Button, Chip, Stack, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost } from '@/lib/api';

export type CporExportRecord = {
  export_version: number;
  file_name: string | null;
  checksum_sha256: string | null;
  actor: string | null;
  created_at: string | null;
  is_latest_for_version: boolean;
  flags_present: string[];
};

export function cporExportFileHref(caseId: number, exportVersion: number): string {
  return `/api/v1/cpor/cases/${caseId}/exports/${exportVersion}/file`;
}

/**
 * Export history plus the Generate action for one CPOR case. Same endpoints as the original
 * workspace tab: `GET …/exports`, `POST …/export`, `GET …/exports/{version}/file`.
 */
export function CporExportsPanel({ caseId }: { caseId: number }) {
  const q = useQuery({
    queryKey: ['cpor', 'exports', caseId],
    queryFn: ({ signal }) => apiGet<{ exports: CporExportRecord[] }>(`/api/v1/cpor/cases/${caseId}/exports`, { signal }),
    enabled: caseId > 0,
  });
  const generate = useMutation({
    mutationFn: () => apiPost(`/api/v1/cpor/cases/${caseId}/export`, {}),
    onSuccess: async () => {
      await q.refetch();
    },
  });
  const exports = q.data?.exports ?? [];

  const generateButton = (
    <Button
      variant="contained"
      size="small"
      disabled={generate.isPending}
      onClick={() => generate.mutate()}
      data-testid="cpor-generate-export"
      sx={{ alignSelf: 'flex-start' }}
    >
      {generate.isPending ? 'Generating…' : 'Generate export'}
    </Button>
  );

  return (
    <Stack spacing={1.5} data-testid="cpor-exports">
      {generate.isError ? (
        <Alert severity="error">{String((generate.error as Error)?.message ?? 'Export failed')}</Alert>
      ) : null}
      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.isError ? new Error(String((q.error as Error)?.message ?? 'Failed to load exports')) : null}
        onRetry={() => void q.refetch()}
        isEmpty={exports.length === 0}
        empty={{
          title: 'No exports yet',
          description: 'Generate the tenant-format export for this case. Every export is versioned and kept; the latest per version is marked.',
          primary: { label: generate.isPending ? 'Generating…' : 'Generate export', onClick: () => generate.mutate() },
        }}
        loadingLabel="Loading exports…"
      >
        <Stack spacing={1.5}>
          {generateButton}
          {exports.map((ex, i) => (
            <Stack
              key={`${ex.export_version}-${i}`}
              direction="row"
              spacing={1}
              alignItems="center"
              flexWrap="wrap"
              useFlexGap
              data-testid={`cpor-export-v${ex.export_version}`}
            >
              <Typography variant="body2">
                v{ex.export_version} · {ex.created_at ?? '—'} · {ex.actor ?? '—'} · {ex.file_name ?? 'file name not stored'}
                {ex.is_latest_for_version ? ' (latest)' : ''}
              </Typography>
              {(ex.flags_present ?? []).map((f) => (
                <Chip key={f} size="small" label={f} variant="outlined" />
              ))}
              <Button size="small" href={cporExportFileHref(caseId, ex.export_version)} target="_blank" rel="noreferrer">
                Download
              </Button>
            </Stack>
          ))}
        </Stack>
      </ModuleDataSection>
    </Stack>
  );
}

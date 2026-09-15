'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

import { CstImportJobResolutionSection } from '@/app/(app)/admin/imports/CstImportJobResolutionSection';
import { DsiImportJobResolutionSection } from '@/app/(app)/admin/imports/DsiImportJobResolutionSection';
import { ShipmentEntityStewardPanel } from '@/app/(app)/admin/shipment-evidence/ShipmentEntityStewardPanel';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import {
  cstTabForEntityType,
  dsiTabForEntityType,
  parsePositiveInt,
  shipmentTabForEntityType,
  stewardResolveEngine,
} from './stewardQueueResolve';

type ImportJobDetail = {
  id: number;
  file_name?: string | null;
  template_slug?: string | null;
  status?: string | null;
};

export function StewardResolveWorkspace() {
  const search = useSearchParams();
  const jobId = parsePositiveInt(search.get('job'));
  const entityType = (search.get('entity_type') || '').trim();
  const token = (search.get('token') || '').trim();
  const candidateId = parsePositiveInt(search.get('candidate'));
  const engine = stewardResolveEngine(entityType);

  const jobQ = useQuery({
    queryKey: ['import-job', jobId, 'steward-resolve'],
    queryFn: ({ signal }) => apiGet<ImportJobDetail>(`/api/v1/imports/jobs/${jobId}`, { signal }),
    enabled: jobId != null,
  });

  if (jobId == null) {
    return (
      <Alert severity="warning" data-testid="steward-resolve-missing-job">
        Steward resolve needs a job id. <Button component={NextLink} href="/admin/mappings" size="small">Back to queue</Button>
      </Alert>
    );
  }

  if (!engine) {
    return (
      <Alert severity="info" data-testid="steward-resolve-uncovered">
        No existing steward engine for <code>{entityType || 'this type'}</code>.{' '}
        <Button component={NextLink} href="/admin/mappings" size="small">
          Back to queue
        </Button>
      </Alert>
    );
  }

  const job = jobQ.data;
  const subtitle = [
    token || null,
    entityType || null,
    job?.file_name || null,
    job?.status || null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Box data-testid="steward-resolve-workspace">
      <Panel
        flush
        title={`Resolve job #${jobId}`}
        subtitle={subtitle || 'Opening the existing steward for this token — not the import wizard.'}
        actions={
          <Button component={NextLink} href="/admin/mappings" size="small" data-testid="steward-resolve-back">
            Back to queue
          </Button>
        }
      >
        <Stack spacing={1.5} sx={{ px: 2, pb: 2 }}>
          {jobQ.isError ? (
            <Alert severity="error">{toQueryError(jobQ.error)?.message ?? 'Could not load this job.'}</Alert>
          ) : null}
          <Typography variant="body2" color="text.secondary">
            Map this token in the job steward. Alias memory is the master mapping; this leaf does not re-ask
            already-mapped parties unless you chose to show them.
          </Typography>
          {engine === 'dsi' ? (
            <DsiImportJobResolutionSection
              importJobId={jobId}
              initialTab={dsiTabForEntityType(entityType) ?? undefined}
              focusNormalizedKey={token || undefined}
              focusCandidateId={candidateId ?? undefined}
              onInvalidate={() => undefined}
            />
          ) : null}
          {engine === 'cst' ? (
            <CstImportJobResolutionSection
              importJobId={jobId}
              initialTab={cstTabForEntityType(entityType) ?? undefined}
              initialSearch={token || undefined}
              focusNormalizedKey={token || undefined}
              onInvalidate={() => undefined}
            />
          ) : null}
          {engine === 'shipment' ? (
            <ShipmentEntityStewardPanel
              importJobId={jobId}
              initialTab={shipmentTabForEntityType(entityType) ?? undefined}
              initialSearch={token || undefined}
            />
          ) : null}
        </Stack>
      </Panel>
    </Box>
  );
}

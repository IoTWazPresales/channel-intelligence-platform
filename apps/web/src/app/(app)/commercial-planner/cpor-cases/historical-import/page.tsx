'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { CanonicalColumnMappingPanel } from '@/features/import-mapping/CanonicalColumnMappingPanel';
import { ImportStewardCandidateWorkspace } from '@/features/import-steward/ImportStewardCandidateWorkspace';
import type { ImportStewardCandidateRowBase } from '@/features/import-steward/importStewardCandidateWorkspace.types';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';

type Source = { id: number; code: string; name: string; import_template_slug?: string | null };
type Profile = {
  id: number;
  profile_code: string;
  display_name: string;
  column_map_json: Record<string, string[]>;
  sheet_roles_json: Record<string, string>;
  is_default: boolean;
};
type Summary = {
  id: number;
  stage: string;
  status: string;
  file_name: string | null;
  staging_count: number;
  unresolved_counts: Record<string, number>;
  cases_ready: number;
  cases_blocked: number;
  cpor_historical?: Record<string, unknown>;
};
type Candidate = {
  entity: string;
  token: string;
  row_count: number;
  status: string;
};
type StewardRow = ImportStewardCandidateRowBase & { token: string };

type ProductPick = { id: number; sku: string; name: string };
type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type DimPick = ProductPick | CustomerPick | DistributorPick;

function tokenId(token: string): number {
  let h = 0;
  for (let i = 0; i < token.length; i += 1) h = (h * 31 + token.charCodeAt(i)) | 0;
  return Math.abs(h) || 1;
}

export default function CporHistoricalImportPage() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [entity, setEntity] = useState<'product' | 'customer' | 'distributor'>('product');
  const [mapTarget, setMapTarget] = useState<DimPick | null>(null);
  const [selectedToken, setSelectedToken] = useState<string | null>(null);
  const [step, setStep] = useState(0);

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
    queryKey: ['cpor', 'historical', 'summary', jobId],
    enabled: jobId != null,
    refetchInterval: (q) => ((q.state.data as Summary | undefined)?.status === 'running' ? 1500 : false),
    queryFn: ({ signal }) =>
      apiGet<Summary>(`/api/v1/cpor/historical-import/jobs/${jobId}/summary`, {
        signal,
        headers: { 'X-User-Role': 'admin' },
      }),
  });

  const { data: candidates } = useQuery({
    queryKey: ['cpor', 'historical', 'candidates', jobId, entity],
    enabled: jobId != null,
    queryFn: ({ signal }) =>
      apiGet<{ candidates: Candidate[]; counts: Record<string, number> }>(
        `/api/v1/cpor/historical-import/jobs/${jobId}/candidates?entity=${entity}`,
        { signal, headers: { 'X-User-Role': 'admin' } },
      ),
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || sourceId == null) throw new Error('Pick a workbook and ensure source exists');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      fd.append('file', file);
      fd.append('run_sync', 'true');
      fd.append('import_mode', 'validate');
      return apiPostFormData<{ id: number; stage: string; status: string }>('/api/v1/imports/jobs', fd);
    },
    onSuccess: (res) => {
      setJobId(res.id);
      setStep(1);
      void qc.invalidateQueries({ queryKey: ['cpor', 'historical'] });
    },
  });

  const mapToken = useMutation({
    mutationFn: () =>
      apiPost(
        `/api/v1/cpor/historical-import/jobs/${jobId}/map-token`,
        { entity, token: selectedToken, dim_id: mapTarget!.id },
        { headers: { 'X-User-Role': 'admin' } },
      ),
    onSuccess: async () => {
      setSelectedToken(null);
      setMapTarget(null);
      await qc.invalidateQueries({ queryKey: ['cpor', 'historical'] });
      await refetchSummary();
    },
  });

  const apply = useMutation({
    mutationFn: () =>
      apiPost<{ async: boolean; task_id: string | null }>(
        `/api/v1/cpor/historical-import/jobs/${jobId}/apply`,
        { confirm: true },
        { headers: { 'X-User-Role': 'admin' } },
      ),
    onSuccess: async () => {
      setStep(2);
      await refetchSummary();
    },
  });

  const stewardRows: StewardRow[] = useMemo(
    () =>
      (candidates?.candidates ?? []).map((c) => ({
        id: tokenId(c.token),
        entity_type: c.entity,
        normalized_key: c.token,
        token: c.token,
        row_count: c.row_count,
        total_units: null,
        total_reported_value: null,
        sample_raw_values: [c.token],
        status: c.status,
        match_reason: null,
        confidence_score: null,
        context: null,
      })),
    [candidates],
  );

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

  const fetchDimOptions = useCallback(
    async (q: string, signal: AbortSignal): Promise<DimPick[]> => {
      if (entity === 'product') {
        const res = await apiGet<{ items: ProductPick[] }>(
          `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
          { signal },
        );
        return res.items ?? [];
      }
      if (entity === 'customer') {
        const res = await apiGet<{ items: CustomerPick[] }>(
          `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
          { signal },
        );
        return res.items ?? [];
      }
      const res = await apiGet<{ items: DistributorPick[] }>(
        `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
        { signal },
      );
      return res.items ?? [];
    },
    [entity],
  );

  const dimLabel = useCallback((o: DimPick) => {
    if ('sku' in o) return `${o.sku} — ${o.name}`;
    if ('customer_code' in o) return `${o.customer_code} — ${o.customer_name}`;
    return `${o.distributor_code} — ${o.distributor_name}`;
  }, []);

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
        Upload an ASUS-style tracking workbook. Settled Results are stored as a frozen snapshot (parity flags
        only). Unresolved entities block that case only — never auto-create masters.
      </Alert>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        {['Upload & map', 'Resolve entities', 'Apply'].map((label, i) => (
          <Chip
            key={label}
            label={`${i + 1}. ${label}`}
            color={step === i ? 'primary' : 'default'}
            variant={step === i ? 'filled' : 'outlined'}
            onClick={() => (jobId != null || i === 0 ? setStep(i) : undefined)}
          />
        ))}
      </Stack>

      {step === 0 ? (
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
              <CanonicalColumnMappingPanel
                fileHeaders={Object.values(profile.column_map_json || {}).flat()}
                draft={mappingDraft}
                onChange={() => undefined}
                targetOptions={targetOptions}
                disabled
                testIdPrefix="cpor-historical"
              />
            </Box>
          ) : null}
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
            {upload.isPending ? 'Validating…' : 'Upload & validate'}
          </Button>
          {upload.isError ? <Alert severity="error">{String((upload.error as Error).message)}</Alert> : null}
        </Stack>
      ) : null}

      {step >= 1 && jobId != null ? (
        <Stack spacing={2}>
          {summary ? (
            <Alert severity="success">
              Job {summary.id} · stage {summary.stage} · {summary.staging_count} staging rows ·{' '}
              {summary.cases_ready} cases ready · {summary.cases_blocked} blocked
            </Alert>
          ) : null}

          <Tabs
            value={entity}
            onChange={(_, v) => {
              setEntity(v);
              setMapTarget(null);
            }}
            data-testid="cpor-historical-entity-tabs"
          >
            <Tab
              value="product"
              label={`Product (${summary?.unresolved_counts?.product ?? candidates?.counts?.product ?? 0})`}
            />
            <Tab
              value="customer"
              label={`Customer (${summary?.unresolved_counts?.customer ?? candidates?.counts?.customer ?? 0})`}
            />
            <Tab
              value="distributor"
              label={`Distributor (${summary?.unresolved_counts?.distributor ?? candidates?.counts?.distributor ?? 0})`}
            />
          </Tabs>

          <ImportStewardCandidateWorkspace
            listDomainId="cpor-historical"
            importJobId={jobId}
            copy={{
              title: 'Unresolved tokens',
              description:
                'Map each token to an existing master record. Unresolved tokens block that case only.',
              emptyOpenListMessage: 'All tokens resolved for this entity.',
              emptyFilteredMessage: 'No matching tokens.',
            }}
            openRows={stewardRows}
            filteredRows={stewardRows}
            isLoading={false}
            busy={mapToken.isPending}
            columns={[
              { id: 'token', header: 'Token', cell: (r) => r.token },
              { id: 'rows', header: 'Rows', cell: (r) => r.row_count },
              { id: 'status', header: 'Status', cell: (r) => r.status },
            ]}
            onRowClick={(row) => setSelectedToken(row.token)}
            rootTestId="cpor-historical-steward"
          />

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="flex-start">
            <TextField
              size="small"
              label="Selected token"
              value={selectedToken ?? ''}
              onChange={(e) => setSelectedToken(e.target.value || null)}
              sx={{ minWidth: 240 }}
            />
            <Box sx={{ minWidth: 280, flex: 1 }}>
              <EntitySearchAutocomplete<DimPick>
                label={`Map ${entity} to…`}
                value={mapTarget}
                onChange={setMapTarget}
                fetchOptions={fetchDimOptions}
                getOptionLabel={dimLabel}
              />
            </Box>
            <Button
              variant="contained"
              disabled={!selectedToken || !mapTarget || mapToken.isPending}
              onClick={() => mapToken.mutate()}
              data-testid="cpor-historical-map-token"
            >
              Map token
            </Button>
          </Stack>

          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button
              variant="contained"
              color="warning"
              disabled={apply.isPending || (summary?.cases_ready ?? 0) < 1}
              onClick={() => apply.mutate()}
              data-testid="cpor-historical-apply"
            >
              {apply.isPending ? 'Applying…' : `Apply ${summary?.cases_ready ?? 0} ready case(s)`}
            </Button>
            <Button component={Link} href="/commercial-planner/cpor-cases" variant="text">
              Back to cases
            </Button>
          </Stack>
          {apply.isError ? <Alert severity="error">{String((apply.error as Error).message)}</Alert> : null}
        </Stack>
      ) : null}

      {step === 2 && summary ? (
        <Alert severity="info" sx={{ mt: 2 }}>
          Apply finished with status <strong>{summary.status}</strong>. Ready cases land with{' '}
          <code>origin=historical_import</code>. Blocked cases stay staged for further mapping.
        </Alert>
      ) : null}
    </>
  );
}

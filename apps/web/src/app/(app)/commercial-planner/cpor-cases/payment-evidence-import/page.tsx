'use client';

import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPost, apiPostFormData, safeDisplayError } from '@/lib/api';

type Source = { id: number; code: string; name: string };
type Profile = { id: number; profile_code: string; display_name: string; is_default: boolean };
type Summary = {
  job_id: number;
  status: string;
  stage: string;
  summary: {
    row_count: number;
    linked_case_count: number;
    unlinked_case_count: number;
    shell_marked_count: number;
    customer_unresolved_count: number;
    distributor_unresolved_count: number;
    distinct_case_codes: number;
    amount_sum: number;
  };
};
type Candidate = {
  token: string;
  row_count: number;
  sample_case_codes?: string[];
  create_shell_case?: boolean;
  resolved_customer_id?: number | null;
};
type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };

export default function CporPaymentEvidenceImportPage() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [entityTab, setEntityTab] = useState<'customer' | 'distributor' | 'case'>('customer');
  const [mapToken, setMapToken] = useState<Candidate | null>(null);
  const [mapTarget, setMapTarget] = useState<CustomerPick | DistributorPick | null>(null);
  const [shellAlso, setShellAlso] = useState(false);

  const { data: profiles } = useQuery({
    queryKey: ['cpor', 'payment', 'profiles'],
    queryFn: ({ signal }) =>
      apiGet<{ profiles: Profile[] }>('/api/v1/cpor/payment-evidence/profiles', {
        signal,
      }),
  });
  const profile = profiles?.profiles?.find((p) => p.is_default) ?? profiles?.profiles?.[0];

  const { data: sources } = useQuery({
    queryKey: ['imports', 'sources', 'cpor_payment_evidence'],
    enabled: !!profiles,
    queryFn: ({ signal }) =>
      apiGet<Source[]>(`/api/v1/imports/sources?template_slug=cpor_payment_evidence`, {
        signal,
      }),
  });
  const sourceId = sources?.[0]?.id ?? null;

  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['cpor', 'payment', 'summary', jobId],
    enabled: jobId != null,
    queryFn: ({ signal }) =>
      apiGet<Summary>(`/api/v1/cpor/payment-evidence/jobs/${jobId}/summary`, { signal }),
  });

  const { data: candidates, refetch: refetchCandidates } = useQuery({
    queryKey: ['cpor', 'payment', 'candidates', jobId, entityTab],
    enabled: jobId != null,
    queryFn: ({ signal }) =>
      apiGet<{ items: Candidate[]; total: number }>(
        `/api/v1/cpor/payment-evidence/jobs/${jobId}/candidates?entity=${entityTab}`,
        { signal },
      ),
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || sourceId == null) throw new Error('Select a file and ensure source exists');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      fd.append('file', file);
      fd.append('import_mode', 'validate');
      fd.append('run_sync', 'true');
      return apiPostFormData<{ id: number }>('/api/v1/imports/jobs', fd);
    },
    onSuccess: async (job) => {
      setJobId(job.id);
      await qc.invalidateQueries({ queryKey: ['cpor', 'payment'] });
    },
  });

  const apply = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/cpor/payment-evidence/jobs/${jobId}/apply`, { confirm: true }),
    onSuccess: async () => {
      await refetchSummary();
    },
  });

  const mapMut = useMutation({
    mutationFn: async () => {
      if (!mapToken || !mapTarget || jobId == null) throw new Error('Pick token and target');
      if (entityTab === 'case') {
        return apiPost(`/api/v1/cpor/payment-evidence/jobs/${jobId}/mark-shell-case`, {
          case_code: mapToken.token,
          enabled: true,
        });
      }
      return apiPost(`/api/v1/cpor/payment-evidence/jobs/${jobId}/map-token`, {
        entity: entityTab,
        token: mapToken.token,
        dim_id: mapTarget.id,
        create_shell_case: entityTab === 'customer' ? shellAlso : undefined,
      });
    },
    onSuccess: async () => {
      setMapToken(null);
      setMapTarget(null);
      await refetchCandidates();
      await refetchSummary();
    },
  });

  const s = summary?.summary;

  return (
    <>
      <FundingChrome />
      <Alert severity="info" sx={{ mb: 2 }}>
        Generic payment evidence — profile maps tenant columns onto case ID, credit note, statuses,
        amount, currency, customer, distributor, description. Case status from file is evidence-only.
        {profile ? (
          <>
            {' '}
            Active profile: <strong>{profile.display_name}</strong> ({profile.profile_code}).
          </>
        ) : null}
      </Alert>

      <Stack spacing={2} sx={{ maxWidth: 960 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button variant="outlined" component="label" data-testid="cpor-payment-file">
            Choose workbook
            <input
              hidden
              type="file"
              accept=".xlsx,.xlsm,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          <Typography variant="body2">{file?.name ?? 'No file selected'}</Typography>
          <Button
            variant="contained"
            disabled={!file || sourceId == null || upload.isPending}
            onClick={() => upload.mutate()}
            data-testid="cpor-payment-upload"
          >
            Upload & validate
          </Button>
          <Button component={Link} href="/commercial-planner/cpor-cases">
            Back to cases
          </Button>
        </Stack>
        {upload.isError ? (
          <Alert severity="error">{safeDisplayError(upload.error)}</Alert>
        ) : null}

        {jobId != null && s ? (
          <Alert severity="success" data-testid="cpor-payment-summary">
            Job #{jobId}: {s.row_count} rows · {s.distinct_case_codes} cases · linked{' '}
            {s.linked_case_count} · unlinked {s.unlinked_case_count} · shell-marked{' '}
            {s.shell_marked_count} · customer gaps {s.customer_unresolved_count} · amount sum{' '}
            {Number(s.amount_sum || 0).toFixed(2)}
          </Alert>
        ) : null}

        {jobId != null ? (
          <>
            <Tabs
              value={entityTab}
              onChange={(_, v) => setEntityTab(v)}
              data-testid="cpor-payment-steward-tabs"
            >
              <Tab value="customer" label="Customers" />
              <Tab value="distributor" label="Distributors" />
              <Tab value="case" label="Unlinked cases" />
            </Tabs>
            <Stack spacing={1}>
              {(candidates?.items ?? []).slice(0, 40).map((c) => (
                <Stack
                  key={c.token}
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  sx={{ borderBottom: '1px solid', borderColor: 'divider', py: 0.5 }}
                >
                  <Typography sx={{ flex: 1 }} variant="body2">
                    <strong>{c.token}</strong> · {c.row_count} rows
                    {c.sample_case_codes?.length ? ` · e.g. ${c.sample_case_codes.join(', ')}` : ''}
                    {c.create_shell_case ? ' · shell marked' : ''}
                  </Typography>
                  <Button size="small" onClick={() => setMapToken(c)}>
                    {entityTab === 'case' ? 'Mark shell' : 'Map'}
                  </Button>
                </Stack>
              ))}
              {(candidates?.items?.length ?? 0) === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No unresolved {entityTab} tokens.
                </Typography>
              ) : null}
            </Stack>

            {mapToken ? (
              <Stack spacing={1} sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="subtitle2">
                  {entityTab === 'case' ? 'Create shell case for' : 'Map'} {mapToken.token}
                </Typography>
                {entityTab === 'customer' ? (
                  <>
                    <EntitySearchAutocomplete<CustomerPick>
                      label="Customer"
                      value={mapTarget as CustomerPick | null}
                      onChange={(v) => setMapTarget(v)}
                      getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                      fetchOptions={async (query, signal) => {
                        const res = await apiGet<{ items: CustomerPick[] }>(
                          `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(query)}`,
                          { signal },
                        );
                        return res.items ?? [];
                      }}
                    />
                    <FormControlLabel
                      control={
                        <Checkbox checked={shellAlso} onChange={(_, v) => setShellAlso(v)} />
                      }
                      label="Also mark unlinked cases for this customer to create shell cases on apply"
                    />
                  </>
                ) : null}
                {entityTab === 'distributor' ? (
                  <EntitySearchAutocomplete<DistributorPick>
                    label="Distributor"
                    value={mapTarget as DistributorPick | null}
                    onChange={(v) => setMapTarget(v)}
                    getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
                    fetchOptions={async (query, signal) => {
                      const res = await apiGet<{ items: DistributorPick[] }>(
                        `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(query)}`,
                        { signal },
                      );
                      return res.items ?? [];
                    }}
                  />
                ) : null}
                {entityTab === 'case' ? (
                  <Alert severity="warning">
                    Shell cases need a resolved customer on the staging rows. Map the customer token
                    first, then mark shell, then apply.
                  </Alert>
                ) : null}
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="contained"
                    disabled={mapMut.isPending || (entityTab !== 'case' && !mapTarget)}
                    onClick={() => mapMut.mutate()}
                  >
                    Confirm
                  </Button>
                  <Button onClick={() => setMapToken(null)}>Cancel</Button>
                </Stack>
                {mapMut.isError ? (
                  <Alert severity="error">{safeDisplayError(mapMut.error)}</Alert>
                ) : null}
              </Stack>
            ) : null}

            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                color="secondary"
                disabled={apply.isPending}
                onClick={() => apply.mutate()}
                data-testid="cpor-payment-apply"
              >
                Apply evidence
              </Button>
              {apply.isSuccess ? (
                <Alert severity="success">Applied — evidence upserted (and shells if marked).</Alert>
              ) : null}
              {apply.isError ? (
                <Alert severity="error">{safeDisplayError(apply.error)}</Alert>
              ) : null}
            </Stack>
          </>
        ) : null}
      </Stack>
    </>
  );
}

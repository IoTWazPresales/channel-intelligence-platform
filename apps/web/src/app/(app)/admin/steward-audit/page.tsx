'use client';

import {
  Alert,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type AuditEvent = {
  id: number;
  created_at: string | null;
  actor: string;
  action: string;
  importer: string;
  entity_type: string | null;
  entity_token: string | null;
  import_job_id: number | null;
  candidate_id: number | null;
  target_dim: string | null;
  target_id: number | null;
  payload_json: Record<string, unknown> | null;
};

type AuditResponse = {
  tenant_id: string;
  count: number;
  events: AuditEvent[];
};

export default function StewardAuditPage() {
  const { data: me, isError: meError } = useCurrentUser();
  const role = String(me?.role || '').toLowerCase();
  const allowed = role === 'admin' || role === 'steward';

  const [importer, setImporter] = useState('');
  const [jobId, setJobId] = useState('');

  const query = useQuery({
    queryKey: ['admin', 'steward-audit', importer, jobId],
    queryFn: () => {
      const qs = new URLSearchParams();
      qs.set('limit', '200');
      if (importer) qs.set('importer', importer);
      if (jobId.trim()) qs.set('import_job_id', jobId.trim());
      return apiGet<AuditResponse>(`/api/v1/admin/steward-audit?${qs.toString()}`);
    },
    enabled: allowed,
    retry: false,
  });

  const rows = useMemo(() => query.data?.events ?? [], [query.data]);

  if (meError || (me && !allowed)) {
    return (
      <>
        <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Steward audit' }]} title="Steward audit" />
        <Alert severity="warning">Admin or steward role required.</Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Steward audit' }]} title="Steward audit" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Append-only log of steward resolve / map / ignore / provisional / bulk decisions (DSI first).
      </Typography>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <FormControl sx={{ minWidth: 180 }} size="small">
          <InputLabel id="audit-importer-label">Importer</InputLabel>
          <Select
            labelId="audit-importer-label"
            label="Importer"
            value={importer}
            onChange={(ev) => setImporter(ev.target.value)}
            inputProps={{ 'data-testid': 'steward-audit-importer' }}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="dsi">dsi</MenuItem>
            <MenuItem value="shipment">shipment</MenuItem>
            <MenuItem value="cpor">cpor</MenuItem>
            <MenuItem value="cst">cst</MenuItem>
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="Import job id"
          value={jobId}
          onChange={(ev) => setJobId(ev.target.value)}
          inputProps={{ 'data-testid': 'steward-audit-job-id' }}
        />
      </Stack>

      <Paper sx={{ p: 2 }} data-testid="steward-audit-table">
        {query.isError ? (
          <Alert severity="error">{safeDisplayError(query.error)}</Alert>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>When</TableCell>
                <TableCell>Actor</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Importer</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>Job</TableCell>
                <TableCell>Target</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>{e.created_at ? e.created_at.replace('T', ' ').slice(0, 19) : '—'}</TableCell>
                  <TableCell>{e.actor}</TableCell>
                  <TableCell>{e.action}</TableCell>
                  <TableCell>{e.importer}</TableCell>
                  <TableCell>
                    {[e.entity_type, e.entity_token].filter(Boolean).join(': ') || '—'}
                  </TableCell>
                  <TableCell>{e.import_job_id ?? '—'}</TableCell>
                  <TableCell>
                    {e.target_dim && e.target_id != null ? `${e.target_dim}#${e.target_id}` : '—'}
                  </TableCell>
                </TableRow>
              ))}
              {!query.isLoading && rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>No steward audit events yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
      </Paper>
    </>
  );
}

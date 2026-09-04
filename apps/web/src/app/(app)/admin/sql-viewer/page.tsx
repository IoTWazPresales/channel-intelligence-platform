'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type TableMeta = { table_schema: string; table_name: string; table_type: string };

type ExecuteResult = {
  ok: boolean;
  status: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  message: string | null;
  audit_id?: number;
  warning?: string;
};

type AuditItem = {
  id: number;
  actor: string;
  sql_text: string;
  status: string;
  row_count: number | null;
  duration_ms: number | null;
  error_message: string | null;
  created_at: string | null;
};

export default function SqlViewerPage() {
  const qc = useQueryClient();
  const { data: me, isError: meError } = useCurrentUser();
  const role = String(me?.role || '').toLowerCase();
  const allowed = role === 'admin';

  const [sql, setSql] = useState('SELECT current_database() AS db, now() AS as_of');
  const [rowLimit, setRowLimit] = useState(200);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [picked, setPicked] = useState('');

  const tablesQ = useQuery({
    queryKey: ['admin', 'sql-viewer-tables'],
    queryFn: ({ signal }) =>
      apiGet<{ items: TableMeta[] }>('/api/v1/admin/sql-viewer/tables', { signal }),
    enabled: allowed,
    retry: false,
  });

  const auditQ = useQuery({
    queryKey: ['admin', 'sql-viewer-audit'],
    queryFn: ({ signal }) =>
      apiGet<{ items: AuditItem[] }>('/api/v1/admin/sql-viewer/audit?limit=30', { signal }),
    enabled: allowed,
    retry: false,
  });

  const runMut = useMutation({
    mutationFn: async () =>
      apiPost<ExecuteResult>('/api/v1/admin/sql-viewer/execute', {
        sql,
        row_limit: rowLimit,
        timeout_ms: 5000,
      }),
    onSuccess: async (data) => {
      setResult(data);
      await qc.invalidateQueries({ queryKey: ['admin', 'sql-viewer-audit'] });
    },
    onError: async (err) => {
      // 400 refused still includes detail payload from FastAPI
      const msg = safeDisplayError(err);
      setResult({
        ok: false,
        status: 'refused',
        columns: [],
        rows: [],
        row_count: 0,
        truncated: false,
        duration_ms: 0,
        message: msg,
      });
      await qc.invalidateQueries({ queryKey: ['admin', 'sql-viewer-audit'] });
    },
  });

  const tableOptions = useMemo(() => tablesQ.data?.items ?? [], [tablesQ.data]);

  if (meError || (me && !allowed)) {
    return (
      <>
        <PageHeader {...navPageChrome('/admin/sql-viewer')} />
        <Alert severity="warning" data-testid="sql-viewer-forbidden">
          Admin role required. Raw SQL is not available to planners or viewers — use Reports for
          governed metrics.
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader {...navPageChrome('/admin/sql-viewer')} />
      <Alert severity="warning" sx={{ mb: 2 }} data-testid="sql-viewer-warning">
        Admin-only read-only console. Results are <strong>not</strong> governed metrics — prefer Report
        builder for fill rate, WoC, and CPOR numbers. Every query is audited. Timeout 5s · row cap{' '}
        {rowLimit}.
      </Alert>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} alignItems="stretch">
        <Stack spacing={2} sx={{ flex: 1, minWidth: 0 }}>
          <Paper sx={{ p: 2 }} data-testid="sql-viewer-author">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1.5 }}>
              <FormControl size="small" sx={{ minWidth: 260 }}>
                <InputLabel id="sql-table-label">Browse table</InputLabel>
                <Select
                  labelId="sql-table-label"
                  label="Browse table"
                  value={picked}
                  data-testid="sql-viewer-table-select"
                  onChange={(e) => {
                    const v = String(e.target.value);
                    setPicked(v);
                    if (!v) return;
                    const [schema, name] = v.split('.');
                    const q = (ident: string) => `"${ident.replace(/"/g, '""')}"`;
                    setSql(`SELECT * FROM ${q(schema)}.${q(name)} LIMIT ${rowLimit}`);
                  }}
                >
                  <MenuItem value="">
                    <em>Pick a table…</em>
                  </MenuItem>
                  {tableOptions.map((t) => {
                    const key = `${t.table_schema}.${t.table_name}`;
                    return (
                      <MenuItem key={key} value={key}>
                        {key}
                      </MenuItem>
                    );
                  })}
                </Select>
              </FormControl>
              <TextField
                size="small"
                type="number"
                label="Row cap"
                value={rowLimit}
                onChange={(e) => setRowLimit(Math.max(1, Math.min(1000, Number(e.target.value) || 200)))}
                sx={{ width: 120 }}
                inputProps={{ 'data-testid': 'sql-viewer-row-cap' }}
              />
              <Button
                variant="contained"
                onClick={() => runMut.mutate()}
                disabled={runMut.isPending || !sql.trim()}
                data-testid="sql-viewer-run"
              >
                {runMut.isPending ? 'Running…' : 'Run'}
              </Button>
            </Stack>
            <TextField
              label="SQL (SELECT / WITH / EXPLAIN / SHOW only)"
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              fullWidth
              multiline
              minRows={6}
              inputProps={{ 'data-testid': 'sql-viewer-sql' }}
            />
          </Paper>

          {result && (
            <Paper sx={{ p: 2 }} data-testid="sql-viewer-result">
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
                <Chip
                  size="small"
                  label={result.status}
                  color={result.ok ? 'success' : 'warning'}
                  data-testid="sql-viewer-status"
                />
                <Typography variant="caption" color="text.secondary">
                  {result.row_count} rows · {result.duration_ms} ms
                  {result.truncated ? ' · truncated' : ''}
                  {result.audit_id != null ? ` · audit #${result.audit_id}` : ''}
                </Typography>
              </Stack>
              {result.message && (
                <Alert severity={result.ok ? 'info' : 'error'} sx={{ mb: 1 }}>
                  {result.message}
                </Alert>
              )}
              {result.warning && (
                <Alert severity="info" sx={{ mb: 1 }}>
                  {result.warning}
                </Alert>
              )}
              {result.columns.length > 0 && (
                <Box sx={{ overflow: 'auto', maxHeight: 420 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        {result.columns.map((c) => (
                          <TableCell key={c}>{c}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {result.rows.map((row, i) => (
                        <TableRow key={i}>
                          {row.map((cell, j) => (
                            <TableCell key={j}>
                              {cell == null ? '—' : typeof cell === 'object' ? JSON.stringify(cell) : String(cell)}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </Paper>
          )}
        </Stack>

        <Paper sx={{ p: 2, width: { lg: 340 }, flexShrink: 0 }} data-testid="sql-viewer-audit-panel">
          <Typography variant="subtitle1" fontWeight={700} gutterBottom>
            Audit log
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Who ran what (tenant-scoped).
          </Typography>
          {auditQ.isError && (
            <Alert severity="warning">Audit unavailable — apply alembic 20260801_0008.</Alert>
          )}
          <Stack spacing={1}>
            {(auditQ.data?.items ?? []).map((a) => (
              <Box key={a.id} sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  #{a.id} · {a.actor} · {a.status} · {a.duration_ms ?? '—'}ms
                </Typography>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }} noWrap>
                  {a.sql_text}
                </Typography>
              </Box>
            ))}
            {!auditQ.isLoading && (auditQ.data?.items?.length ?? 0) === 0 && (
              <Typography variant="body2" color="text.secondary">
                No queries yet.
              </Typography>
            )}
          </Stack>
        </Paper>
      </Stack>
    </>
  );
}

'use client';

import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

export type BulkPromoteMappingRow = {
  tmp_code: string;
  new_code: string;
  note?: string | null;
};

type BatchRowResult = {
  tmp_code: string;
  new_code: string;
  note?: string | null;
  customer_id: number | null;
  status: 'ready' | 'blocked' | 'skipped_blank' | 'applied';
  reasons: string[];
  collision?: { customer_id?: number; code?: string; note?: string } | null;
  warnings?: string[];
  outcome?: 'applied' | 'blocked' | 'skipped' | null;
  old_code?: string;
  new_status?: string;
};

type BatchResponse = {
  dry_run: boolean;
  rows: BatchRowResult[];
  summary: {
    ready: number;
    blocked: number;
    skipped: number;
    applied: number;
    total: number;
  };
};

type Props = {
  open: boolean;
  onClose: () => void;
};

/** Parse paste/CSV: tmp_code,new_code[,note]. Header optional. */
export function parseBulkPromoteCsv(text: string): BulkPromoteMappingRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('tmp_code') || (first.includes('tmp') && first.includes('new'));
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: BulkPromoteMappingRow[] = [];
  for (const line of dataLines) {
    const parts = line.split(',').map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 1) continue;
    const [tmp_code, new_code = '', note] = parts;
    if (!tmp_code && !new_code) continue;
    rows.push({
      tmp_code: tmp_code || '',
      new_code: new_code || '',
      note: note || undefined,
    });
  }
  return rows;
}

function statusChip(status: BatchRowResult['status']) {
  if (status === 'ready') return <Chip size="small" color="success" label="Ready" />;
  if (status === 'applied') return <Chip size="small" color="success" label="Applied" />;
  if (status === 'skipped_blank') return <Chip size="small" label="Skipped (blank)" />;
  return <Chip size="small" color="error" label="Blocked" />;
}

function downloadReportCsv(rows: BatchRowResult[]) {
  const header = 'tmp_code,new_code,status,outcome,reasons,customer_id';
  const lines = rows.map((r) => {
    const reasons = (r.reasons || []).join(';').replace(/"/g, '""');
    return [
      r.tmp_code,
      r.new_code,
      r.status,
      r.outcome ?? '',
      `"${reasons}"`,
      r.customer_id ?? '',
    ].join(',');
  });
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'customer-bulk-promote-report.csv';
  a.click();
  URL.revokeObjectURL(url);
}

export function CustomerBulkPromoteDialog({ open, onClose }: Props) {
  const qc = useQueryClient();
  const [paste, setPaste] = useState('');
  const [step, setStep] = useState<'input' | 'preview' | 'result'>('input');
  const [preview, setPreview] = useState<BatchResponse | null>(null);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapping, setMapping] = useState<BulkPromoteMappingRow[]>([]);

  useEffect(() => {
    if (!open) return;
    setPaste('');
    setStep('input');
    setPreview(null);
    setResult(null);
    setError(null);
    setMapping([]);
  }, [open]);

  const parsedCount = useMemo(() => parseBulkPromoteCsv(paste).length, [paste]);

  const previewMut = useMutation({
    mutationFn: async () => {
      const rows = parseBulkPromoteCsv(paste);
      if (rows.length === 0) throw new Error('Paste at least one tmp_code,new_code row');
      if (rows.length > 500) throw new Error('Max 500 rows per batch');
      setMapping(rows);
      return apiPost<BatchResponse>('/api/v1/customers/promote/batch', {
        rows,
        dry_run: true,
      });
    },
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setError(null);
      setStep('preview');
    },
    onError: (err) => {
      setPreview(null);
      setError(safeDisplayError(err));
    },
  });

  const confirmMut = useMutation({
    mutationFn: async () => {
      if (!mapping.length) throw new Error('No mapping');
      return apiPost<BatchResponse>('/api/v1/customers/promote/batch', {
        rows: mapping,
        dry_run: false,
      });
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setStep('result');
      void qc.invalidateQueries({ queryKey: ['customers'] });
      void qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const readyN = preview?.summary.ready ?? 0;
  const displayRows = result?.rows ?? preview?.rows ?? [];

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      data-testid="customer-bulk-promote-dialog"
    >
      <DialogTitle>Bulk promote provisional customers</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Map existing TMP codes to real business codes. Format:{' '}
            <code>tmp_code,new_code[,note]</code>. Blank new_code rows are skipped. No codes are
            minted here — paste codes from your ERP/import or leave blank until a tenant convention
            exists.
          </Typography>

          {step === 'input' ? (
            <>
              <TextField
                multiline
                minRows={10}
                fullWidth
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
                placeholder={'tmp_code,new_code,note\nTMP-CUST-ABC,ACME-001,steward ok'}
                inputProps={{ 'data-testid': 'bulk-promote-paste' }}
              />
              <Typography variant="caption" color="text.secondary">
                {parsedCount} row{parsedCount === 1 ? '' : 's'} parsed (max 500)
              </Typography>
              <Button variant="outlined" component="label" data-testid="bulk-promote-file">
                Load CSV file
                <input
                  type="file"
                  accept=".csv,text/csv,text/plain"
                  hidden
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    setPaste(await f.text());
                    e.target.value = '';
                  }}
                />
              </Button>
            </>
          ) : null}

          {error ? (
            <Alert severity="error" data-testid="bulk-promote-error">
              {error}
            </Alert>
          ) : null}

          {(step === 'preview' || step === 'result') && displayRows.length ? (
            <Stack spacing={1} data-testid={step === 'result' ? 'bulk-promote-result' : 'bulk-promote-preview'}>
              <Typography variant="subtitle2">
                {step === 'result' ? 'Result' : 'Preview'} · ready {preview?.summary.ready ?? 0} ·
                blocked {result?.summary.blocked ?? preview?.summary.blocked ?? 0} · skipped{' '}
                {result?.summary.skipped ?? preview?.summary.skipped ?? 0}
                {step === 'result' ? ` · applied ${result?.summary.applied ?? 0}` : ''}
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>TMP code</TableCell>
                    <TableCell>New code</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Reasons</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {displayRows.map((r, i) => (
                    <TableRow key={`${r.tmp_code}-${i}`}>
                      <TableCell>{r.tmp_code}</TableCell>
                      <TableCell>{r.new_code || '—'}</TableCell>
                      <TableCell>{statusChip(r.status)}</TableCell>
                      <TableCell>
                        {(r.reasons || []).join(', ') ||
                          (r.collision?.note ? String(r.collision.note) : '—')}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{step === 'result' ? 'Close' : 'Cancel'}</Button>
        {step === 'result' ? (
          <Button
            onClick={() => result && downloadReportCsv(result.rows)}
            data-testid="bulk-promote-download"
          >
            Download report CSV
          </Button>
        ) : null}
        {step === 'input' ? (
          <Button
            variant="contained"
            disabled={!paste.trim() || previewMut.isPending}
            onClick={() => previewMut.mutate()}
            data-testid="bulk-promote-preview-btn"
          >
            {previewMut.isPending ? 'Previewing…' : 'Preview'}
          </Button>
        ) : null}
        {step === 'preview' ? (
          <>
            <Button
              onClick={() => {
                setStep('input');
                setPreview(null);
              }}
            >
              Back
            </Button>
            <Button
              variant="contained"
              disabled={readyN === 0 || confirmMut.isPending}
              onClick={() => confirmMut.mutate()}
              data-testid="bulk-promote-confirm-btn"
            >
              {confirmMut.isPending ? 'Promoting…' : `Promote ${readyN} ready row${readyN === 1 ? '' : 's'}`}
            </Button>
          </>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}

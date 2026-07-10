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
  ToggleButton,
  ToggleButtonGroup,
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

export type MintCandidate = {
  tmp_code: string;
  name?: string;
};

type BatchRowResult = {
  tmp_code: string;
  new_code: string;
  note?: string | null;
  distributor_id: number | null;
  status: 'ready' | 'blocked' | 'skipped_blank' | 'applied';
  reasons: string[];
  collision?: { distributor_id?: number; code?: string; note?: string } | null;
  warnings?: string[];
  outcome?: 'applied' | 'blocked' | 'skipped' | null;
  old_code?: string;
  new_status?: string;
};

type BatchResponse = {
  dry_run: boolean;
  mode?: 'map' | 'mint';
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
  /** Optional grid selection for mint mode (TMP-DIST rows). */
  mintCandidates?: MintCandidate[];
};

export const BULK_PROMOTE_CHUNK_SIZE = 500;

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

/** One tmp_code per line (or comma-first field). */
export function parseMintTmpCodes(text: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const raw = line.trim();
    if (!raw) continue;
    const lower = raw.toLowerCase();
    if (lower === 'tmp_code' || lower.startsWith('tmp_code,')) continue;
    const code = raw.split(',')[0].trim().replace(/^"|"$/g, '');
    if (!code) continue;
    const key = code.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(code);
  }
  return out;
}

/** Split into â‰¤chunkSize batches (client-side chunking for ~4.9k backlog). */
export function chunkRows<T>(rows: T[], chunkSize = BULK_PROMOTE_CHUNK_SIZE): T[][] {
  if (chunkSize < 1) throw new Error('chunkSize must be >= 1');
  const chunks: T[][] = [];
  for (let i = 0; i < rows.length; i += chunkSize) {
    chunks.push(rows.slice(i, i + chunkSize));
  }
  return chunks;
}

function mergeBatchResponses(parts: BatchResponse[], dryRun: boolean): BatchResponse {
  const rows = parts.flatMap((p) => p.rows);
  return {
    dry_run: dryRun,
    mode: parts[0]?.mode,
    rows,
    summary: {
      ready: rows.filter((r) => r.status === 'ready').length,
      blocked: rows.filter((r) => r.status === 'blocked').length,
      skipped: rows.filter((r) => r.status === 'skipped_blank').length,
      applied: rows.filter((r) => r.status === 'applied').length,
      total: rows.length,
    },
  };
}

function statusChip(status: BatchRowResult['status']) {
  if (status === 'ready') return <Chip size="small" color="success" label="Ready" />;
  if (status === 'applied') return <Chip size="small" color="success" label="Applied" />;
  if (status === 'skipped_blank') return <Chip size="small" label="Skipped (blank)" />;
  return <Chip size="small" color="error" label="Blocked" />;
}

function downloadReportCsv(rows: BatchRowResult[]) {
  const header = 'tmp_code,new_code,status,outcome,reasons,distributor_id';
  const lines = rows.map((r) => {
    const reasons = (r.reasons || []).join(';').replace(/"/g, '""');
    return [
      r.tmp_code,
      r.new_code,
      r.status,
      r.outcome ?? '',
      `"${reasons}"`,
      r.distributor_id ?? '',
    ].join(',');
  });
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'distributor-bulk-promote-report.csv';
  a.click();
  URL.revokeObjectURL(url);
}

export function DistributorBulkPromoteDialog({ open, onClose, mintCandidates = [] }: Props) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<'map' | 'mint'>('map');
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
    setMode(mintCandidates.length > 0 ? 'mint' : 'map');
  }, [open, mintCandidates.length]);

  const parsedMapCount = useMemo(() => parseBulkPromoteCsv(paste).length, [paste]);
  const mintCodesFromPaste = useMemo(() => parseMintTmpCodes(paste), [paste]);
  const effectiveMintCodes = useMemo(() => {
    if (mintCandidates.length > 0) {
      const seen = new Set<string>();
      const codes: string[] = [];
      for (const c of mintCandidates) {
        const code = (c.tmp_code || '').trim();
        if (!code) continue;
        const key = code.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        codes.push(code);
      }
      return codes;
    }
    return mintCodesFromPaste;
  }, [mintCandidates, mintCodesFromPaste]);

  const nameByTmp = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of mintCandidates) {
      if (c.tmp_code && c.name) m.set(c.tmp_code.toLowerCase(), c.name);
    }
    return m;
  }, [mintCandidates]);

  const previewMut = useMutation({
    mutationFn: async () => {
      if (mode === 'map') {
        const rows = parseBulkPromoteCsv(paste);
        if (rows.length === 0) throw new Error('Paste at least one tmp_code,new_code row');
        if (rows.length > BULK_PROMOTE_CHUNK_SIZE) {
          throw new Error(`Max ${BULK_PROMOTE_CHUNK_SIZE} rows per batch`);
        }
        setMapping(rows);
        return apiPost<BatchResponse>('/api/v1/distributors/promote/batch', {
          rows,
          dry_run: true,
          mode: 'map',
        });
      }
      const codes = effectiveMintCodes;
      if (codes.length === 0) {
        throw new Error('Select TMP distributors on the grid, or paste tmp_code lines');
      }
      const rows = codes.map((tmp_code) => ({ tmp_code, new_code: '' }));
      setMapping(rows);
      const chunks = chunkRows(rows, BULK_PROMOTE_CHUNK_SIZE);
      const parts: BatchResponse[] = [];
      for (const chunk of chunks) {
        parts.push(
          await apiPost<BatchResponse>('/api/v1/distributors/promote/batch', {
            rows: chunk,
            dry_run: true,
            mode: 'mint',
          })
        );
      }
      return mergeBatchResponses(parts, true);
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
      if (mode === 'map') {
        return apiPost<BatchResponse>('/api/v1/distributors/promote/batch', {
          rows: mapping,
          dry_run: false,
          mode: 'map',
        });
      }
      const chunks = chunkRows(mapping, BULK_PROMOTE_CHUNK_SIZE);
      const parts: BatchResponse[] = [];
      for (const chunk of chunks) {
        parts.push(
          await apiPost<BatchResponse>('/api/v1/distributors/promote/batch', {
            rows: chunk,
            dry_run: false,
            mode: 'mint',
          })
        );
      }
      return mergeBatchResponses(parts, false);
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setStep('result');
      void qc.invalidateQueries({ queryKey: ['distributors'] });
      void qc.invalidateQueries({ queryKey: ['admin-distributors'] });
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const readyN = preview?.summary.ready ?? 0;
  const displayRows = result?.rows ?? preview?.rows ?? [];
  const inputReady =
    mode === 'map' ? Boolean(paste.trim()) : effectiveMintCodes.length > 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      data-testid="distributor-bulk-promote-dialog"
    >
      <DialogTitle>Bulk promote provisional distributors</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          {step === 'input' ? (
            <ToggleButtonGroup
              exclusive
              size="small"
              value={mode}
              onChange={(_, v) => {
                if (v) {
                  setMode(v);
                  setError(null);
                }
              }}
              data-testid="bulk-promote-mode"
            >
              <ToggleButton value="map">CSV / paste map</ToggleButton>
              <ToggleButton value="mint">Mint codes</ToggleButton>
            </ToggleButtonGroup>
          ) : null}

          {mode === 'map' ? (
            <Typography variant="body2" color="text.secondary">
              Map existing TMP codes to real business codes. Format:{' '}
              <code>tmp_code,new_code[,note]</code>. Blank new_code rows are skipped.
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              System-mint Candidate A codes (<code>DIST-000001</code>â€¦). Select TMP rows on the
              distributors grid (selection mode), or paste one <code>tmp_code</code> per line. Preview
              then confirm; batches of {BULK_PROMOTE_CHUNK_SIZE} are sent automatically.
            </Typography>
          )}

          {step === 'input' && mode === 'map' ? (
            <>
              <TextField
                multiline
                minRows={10}
                fullWidth
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
                placeholder={'tmp_code,new_code,note\nTMP-DIST-ABC,MUSTEK-ZA,steward ok'}
                inputProps={{ 'data-testid': 'bulk-promote-paste' }}
              />
              <Typography variant="caption" color="text.secondary">
                {parsedMapCount} row{parsedMapCount === 1 ? '' : 's'} parsed (max{' '}
                {BULK_PROMOTE_CHUNK_SIZE})
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

          {step === 'input' && mode === 'mint' ? (
            <>
              {mintCandidates.length > 0 ? (
                <Alert severity="info" data-testid="bulk-promote-mint-selection">
                  {effectiveMintCodes.length} selected TMP distributor
                  {effectiveMintCodes.length === 1 ? '' : 's'} from the grid.
                </Alert>
              ) : (
                <TextField
                  multiline
                  minRows={8}
                  fullWidth
                  value={paste}
                  onChange={(e) => setPaste(e.target.value)}
                  placeholder={'TMP-DIST-ABC\nTMP-DIST-DEF'}
                  inputProps={{ 'data-testid': 'bulk-promote-mint-paste' }}
                />
              )}
              <Typography variant="caption" color="text.secondary">
                {effectiveMintCodes.length} code{effectiveMintCodes.length === 1 ? '' : 's'} Â·{' '}
                {chunkRows(effectiveMintCodes, BULK_PROMOTE_CHUNK_SIZE).length} request chunk
                {chunkRows(effectiveMintCodes, BULK_PROMOTE_CHUNK_SIZE).length === 1 ? '' : 's'}
              </Typography>
            </>
          ) : null}

          {error ? (
            <Alert severity="error" data-testid="bulk-promote-error">
              {error}
            </Alert>
          ) : null}

          {(step === 'preview' || step === 'result') && displayRows.length ? (
            <Stack
              spacing={1}
              data-testid={step === 'result' ? 'bulk-promote-result' : 'bulk-promote-preview'}
            >
              <Typography variant="subtitle2">
                {step === 'result' ? 'Result' : 'Preview'} Â· ready {preview?.summary.ready ?? 0} Â·
                blocked {result?.summary.blocked ?? preview?.summary.blocked ?? 0} Â· skipped{' '}
                {result?.summary.skipped ?? preview?.summary.skipped ?? 0}
                {step === 'result' ? ` Â· applied ${result?.summary.applied ?? 0}` : ''}
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>TMP code</TableCell>
                    {mode === 'mint' ? <TableCell>Name</TableCell> : null}
                    <TableCell>New code</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Reasons</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {displayRows.map((r, i) => (
                    <TableRow key={`${r.tmp_code}-${i}`}>
                      <TableCell>{r.tmp_code}</TableCell>
                      {mode === 'mint' ? (
                        <TableCell>{nameByTmp.get(r.tmp_code.toLowerCase()) || 'â€”'}</TableCell>
                      ) : null}
                      <TableCell>{r.new_code || 'â€”'}</TableCell>
                      <TableCell>{statusChip(r.status)}</TableCell>
                      <TableCell>
                        {(r.reasons || []).join(', ') ||
                          (r.collision?.note ? String(r.collision.note) : 'â€”')}
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
            disabled={!inputReady || previewMut.isPending}
            onClick={() => previewMut.mutate()}
            data-testid="bulk-promote-preview-btn"
          >
            {previewMut.isPending ? 'Previewingâ€¦' : 'Preview'}
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
              {confirmMut.isPending
                ? 'Promotingâ€¦'
                : `Promote ${readyN} ready row${readyN === 1 ? '' : 's'}`}
            </Button>
          </>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}


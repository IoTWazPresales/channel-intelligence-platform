'use client';

import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { apiDownloadBlob, apiPostFormData } from '@/lib/api';

type SkuImportPreviewRow = {
  source_row: number;
  sku: string | null;
  part_number: string | null;
  sales_model: string | null;
  model_name: string | null;
  product_id: number | null;
  product_sku: string | null;
  product_name: string | null;
  match_method: string | null;
  action: string;
  messages: string[];
  blocking: boolean;
  current: Record<string, unknown> | null;
  proposed: Record<string, unknown> | null;
};

type SkuImportPreviewResponse = {
  parse_errors: string[];
  rows: SkuImportPreviewRow[];
  summary: { creates: number; updates: number; errors: number; blocking_errors: number };
  can_apply: boolean;
};

/** The controlled-cost CSV flow extracted from planner defaults. */
export function SkuEconomicsImport() {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importPreview, setImportPreview] = useState<SkuImportPreviewResponse | null>(null);
  const [importApplySummary, setImportApplySummary] = useState<{ applied_creates: number; applied_updates: number } | null>(
    null
  );
  const [importConfirm, setImportConfirm] = useState(false);
  const [importFileLabel, setImportFileLabel] = useState<string | null>(null);
  const lastImportFileRef = useRef<File | null>(null);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ['commercial-planner'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-lines'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-summary'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions'] });
    void qc.invalidateQueries({ queryKey: ['plan-readiness'] });
    void qc.invalidateQueries({ queryKey: ['admin-products'] });
  };

  const previewSkuImport = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<SkuImportPreviewResponse>('/api/v1/commercial-planner/sku-assumptions/import-preview', fd);
    },
    onSuccess: (data) => {
      setImportPreview(data);
      setImportApplySummary(null);
      setImportConfirm(false);
    },
  });

  const applySkuImport = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      return apiPostFormData<{ applied_creates: number; applied_updates: number; summary: unknown }>(
        '/api/v1/commercial-planner/sku-assumptions/import-apply',
        fd
      );
    },
    onSuccess: (data) => {
      setImportApplySummary({ applied_creates: data.applied_creates, applied_updates: data.applied_updates });
      setImportPreview(null);
      setImportFileLabel(null);
      setImportConfirm(false);
      invalidateAll();
    },
  });

  return (
    <Stack spacing={1}>
      <Alert severity="warning" sx={{ mb: 1, py: 0.5 }} data-testid="planner-defaults-sku-bulk-dap-copy">
        <Typography variant="caption" component="div">
          <strong>Controlled cost / PM bottom</strong> must come from an approved cost source. DAP and Rand landed evidence
          are <strong>not</strong> used as controlled cost. Do not add DAP columns to this template.
        </Typography>
      </Alert>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Bulk template: match products by <code>sku</code> first, then <code>part_number</code>, then a unique{' '}
        <code>sales_model</code> + <code>model_name</code> pair. Percent fields accept decimals 0-1 (e.g. 0.15) or percent
        points 1-100 (e.g. 15); values between 1 and 100 are divided by 100. Optional columns{' '}
        <code>notes</code>, <code>source_reference</code>, <code>valid_from</code>, <code>valid_to</code> are ignored for
        persistence.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        <Button
          size="small"
          variant="outlined"
          data-testid="sku-economics-download-template"
          onClick={() =>
            void apiDownloadBlob('/api/v1/commercial-planner/sku-assumptions/import-template', 'sku_economics_template.csv')
          }
        >
          Download template
        </Button>
        <Button
          size="small"
          variant="outlined"
          data-testid="sku-economics-upload-trigger"
          disabled={previewSkuImport.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          Upload SKU economics file
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          aria-label="SKU economics file"
          accept=".csv,text/csv"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (!f) return;
            lastImportFileRef.current = f;
            setImportFileLabel(f.name);
            previewSkuImport.mutate(f);
          }}
        />
        {importFileLabel ? (
          <Typography variant="caption" color="text.secondary">
            Selected: {importFileLabel}
          </Typography>
        ) : null}
      </Stack>
      {previewSkuImport.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          Preview failed: {previewSkuImport.error instanceof Error ? previewSkuImport.error.message : 'Unknown error'}
        </Alert>
      ) : null}
      {importApplySummary ? (
        <Alert
          severity="success"
          sx={{ mb: 1 }}
          onClose={() => setImportApplySummary(null)}
          data-testid="sku-import-apply-summary"
        >
          Applied: {importApplySummary.applied_creates} created, {importApplySummary.applied_updates} updated.
        </Alert>
      ) : null}
      {importPreview?.parse_errors?.length ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {importPreview.parse_errors.map((err) => (
            <Typography key={err} variant="caption" display="block">
              {err}
            </Typography>
          ))}
        </Alert>
      ) : null}
      {importPreview && !importPreview.parse_errors.length ? (
        <Stack spacing={1} sx={{ mb: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Preview: {importPreview.summary.creates} create(s), {importPreview.summary.updates} update(s),{' '}
            {importPreview.summary.blocking_errors} blocking error(s).
          </Typography>
          <FormControlLabel
            control={
              <Checkbox
                checked={importConfirm}
                onChange={(e) => setImportConfirm(e.target.checked)}
                disabled={!importPreview.can_apply || applySkuImport.isPending}
                data-testid="sku-import-confirm-checkbox"
              />
            }
            label="I confirm applying these SKU economics changes to the database."
          />
          <Button
            size="small"
            variant="contained"
            color="primary"
            data-testid="sku-import-apply-btn"
            disabled={
              !importPreview.can_apply ||
              !importConfirm ||
              applySkuImport.isPending ||
              !lastImportFileRef.current
            }
            onClick={() => {
              const f = lastImportFileRef.current;
              if (f) applySkuImport.mutate(f);
            }}
          >
            Apply import
          </Button>
          {applySkuImport.isError ? (
            <Alert severity="error">
              Apply failed: {applySkuImport.error instanceof Error ? applySkuImport.error.message : ''}
            </Alert>
          ) : null}
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Row</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell>Match</TableCell>
                  <TableCell>Current CC</TableCell>
                  <TableCell>Proposed CC</TableCell>
                  <TableCell>FX</TableCell>
                  <TableCell>VAT</TableCell>
                  <TableCell>Reserves</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Messages</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {importPreview.rows.map((r) => (
                  <TableRow key={r.source_row}>
                    <TableCell>{r.source_row}</TableCell>
                    <TableCell>{`${r.product_sku || r.sku || '-'} - ${r.product_name || ''}`}</TableCell>
                    <TableCell>{r.match_method ?? '-'}</TableCell>
                    <TableCell>
                      {r.current
                        ? `${String(r.current.controlled_cost_amount)} ${String(r.current.controlled_cost_currency_code)}`
                        : '-'}
                    </TableCell>
                    <TableCell>
                      {r.proposed
                        ? `${String(r.proposed.controlled_cost_amount)} ${String(r.proposed.controlled_cost_currency_code)}`
                        : '-'}
                    </TableCell>
                    <TableCell>{r.proposed ? String(r.proposed.fx_plan_currency_per_cost_currency) : '-'}</TableCell>
                    <TableCell>{r.proposed ? String(r.proposed.vat_rate_pct) : '-'}</TableCell>
                    <TableCell>
                      {r.proposed
                        ? `${String(r.proposed.reserve_total_pct)} / ${String(r.proposed.promo_reserve_split_pct)}`
                        : '-'}
                    </TableCell>
                    <TableCell>{r.action}</TableCell>
                    <TableCell>{r.messages.join('; ') || '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ) : null}
    </Stack>
  );
}

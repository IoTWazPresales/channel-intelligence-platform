'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiGet, apiPatch, apiPostFormData, safeDisplayError } from '@/lib/api';
import {
  CanonicalColumnMappingPanel,
  type CanonicalRequiredGroup,
  type CanonicalTargetOption,
} from '@/features/import-mapping/CanonicalColumnMappingPanel';

import {
  appendCstUploadOptions,
  CstUploadOptionsFields,
  EMPTY_CST_UPLOAD_OPTIONS,
  suggestYearFromNames,
  type CstUploadOptions,
} from './CstUploadOptions';

const ACCEPT =
  '.csv,.xlsx,.xlsm,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12,application/vnd.ms-excel,text/csv';

const ALLOWED_EXT = ['.csv', '.xlsx', '.xlsm', '.xls'];

export type ReportingCustomer = {
  id: number;
  name: string;
  layout_count: number;
};

export type SavedLayout = {
  id: number;
  customer_id: number;
  name: string;
  headers: string[];
  report_structure_type: string;
  is_hidden: boolean;
};

type FileLayoutInfo = {
  filename: string;
  readable: boolean;
  unreadable_reason?: string | null;
  columns: string[];
  layout_signature: string | null;
  layout: {
    id: number;
    name: string;
    /** The layout maps the older single product column (it keeps loading as before). */
    legacy_product_slot?: boolean;
    /** What the layout maps today, by this file's headers. */
    mapping?: Record<string, string>;
  } | null;
  similar_layout?: { id: number; name: string } | null;
  detected_mapping: Record<string, string>;
  samples: Record<string, string[]>;
};

type BatchProposeResponse = {
  group_count: number;
  file_count: number;
  customer_id?: number;
  files?: FileLayoutInfo[];
  targets?: CanonicalTargetOption[];
};

type BatchJobResult = {
  outcome: 'created' | 'error';
  import_job_id?: number;
  stage?: string | null;
  filenames: string[];
  file_count?: number;
  layouts?: { id: number; name: string }[];
  error?: string;
};

type BatchJobsResponse = {
  group_count: number;
  jobs: BatchJobResult[];
};

/** A column layout not yet saved, or a saved one being re-mapped: the file headers the mapping step is working on. */
type NewLayoutDraft = {
  signature: string;
  /** Set when a saved layout is being re-mapped into the separate identifier columns. */
  layoutId?: number;
  filenames: string[];
  columns: string[];
  samples: Record<string, string[]>;
  similar: { id: number; name: string } | null;
};

export type CstBulkUploadDialogProps = {
  open: boolean;
  onClose: () => void;
  /** First created batch job id — wizard continues with CST steward. */
  onJobsCreated: (jobIds: number[]) => void;
  /** The import mode picked in the wizard: apply loads matched rows as each file is read. */
  importMode?: 'validate' | 'apply';
  /** Reporting customer to start with (from a ?customer= link). */
  initialCustomerId?: number | null;
};

/** The older single product column; offered only while a layout still uses it. */
const LEGACY_PRODUCT_TARGET = 'raw_product_token';

/** A product identifier and a figure to load must be mapped (the same gate the server applies). */
const REQUIRED_GROUPS: CanonicalRequiredGroup[] = [
  {
    id: 'product',
    label: 'Product identifier (part number, barcode, sales model or customer product code)',
    anyOf: [
      'raw_part_number_token',
      'raw_barcode_token',
      'raw_sales_model_token',
      'raw_article_token',
      LEGACY_PRODUCT_TARGET,
    ],
  },
  { id: 'figure', label: 'Units sold or on-hand', anyOf: ['units_sold', 'reported_soh', 'total_sell_amount'] },
];

function extOk(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXT.some((e) => lower.endsWith(e));
}

function stem(name: string): string {
  return name.replace(/\.[^.]+$/, '').trim() || name;
}

function missingGroups(draft: Record<string, string>): string[] {
  const mapped = new Set(Object.values(draft).filter(Boolean));
  return REQUIRED_GROUPS.filter((g) => !g.anyOf.some((t) => mapped.has(t))).map((g) => g.label);
}

function SavedLayouts({ customerId }: { customerId: number }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<number | null>(null);
  const [name, setName] = useState('');
  const { data } = useQuery({
    queryKey: ['cst-layouts', customerId],
    queryFn: ({ signal }) => apiGet<SavedLayout[]>(`/api/v1/imports/cst/layouts?customer_id=${customerId}`, { signal }),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { name?: string; is_hidden?: boolean } }) =>
      apiPatch<SavedLayout>(`/api/v1/imports/cst/layouts/${id}`, body),
    onSuccess: () => {
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['cst-layouts', customerId] });
      void qc.invalidateQueries({ queryKey: ['cst-reporting-customers'] });
    },
  });
  if (!data) return null;
  return (
    <Stack spacing={0.5} data-testid="cst-saved-layouts">
      <Typography variant="caption" color="text.secondary">
        {data.length
          ? `Saved column layouts (${data.length}). A file whose headers match one is mapped automatically.`
          : 'No saved column layout yet. The first file you upload is mapped here and the layout is saved for this customer.'}
      </Typography>
      {data.map((l) =>
        editing === l.id ? (
          <Stack key={l.id} direction="row" spacing={1} alignItems="center">
            <TextField
              size="small"
              value={name}
              onChange={(e) => setName(e.target.value)}
              inputProps={{ 'aria-label': `Name of layout ${l.name}` }}
            />
            <Button
              size="small"
              disabled={!name.trim() || patch.isPending}
              onClick={() => patch.mutate({ id: l.id, body: { name: name.trim() } })}
            >
              Save name
            </Button>
            <Button size="small" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </Stack>
        ) : (
          <Stack key={l.id} direction="row" spacing={1} alignItems="center" data-testid={`cst-layout-${l.id}`}>
            <Chip size="small" variant="outlined" label={l.name} />
            <Typography variant="caption" color="text.secondary">
              {l.headers.length} columns{l.report_structure_type !== 'flat' ? ` · ${l.report_structure_type}` : ''}
            </Typography>
            <Button
              size="small"
              onClick={() => {
                setEditing(l.id);
                setName(l.name);
              }}
            >
              Rename
            </Button>
            <Button
              size="small"
              color="warning"
              disabled={patch.isPending}
              onClick={() => patch.mutate({ id: l.id, body: { is_hidden: true } })}
            >
              Remove
            </Button>
          </Stack>
        )
      )}
      {patch.isError ? <Alert severity="error">{safeDisplayError(patch.error)}</Alert> : null}
    </Stack>
  );
}

/**
 * Customer sell-through upload (N-0111, Warren 2026-10-16). The upload picks a reporting customer, not a
 * source. Each file is matched to one of that customer's saved column layouts by its headers; a file
 * whose headers match none opens the column-mapping step (the shared mapping panel) and the layout is
 * saved for the customer. All files then load into the one sell-through table with its standard columns:
 * files that share a report structure become one import job (per-file period, one steward pass).
 */
export function CstBulkUploadDialog({
  open,
  onClose,
  onJobsCreated,
  importMode = 'validate',
  initialCustomerId = null,
}: CstBulkUploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [customerId, setCustomerId] = useState<number | ''>('');
  // A "missing report" link from the Sell-through tab opens the upload for that customer.
  useEffect(() => {
    if (open && initialCustomerId != null) setCustomerId((c) => (c === '' ? initialCustomerId : c));
  }, [open, initialCustomerId]);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<BatchProposeResponse | null>(null);
  const [results, setResults] = useState<BatchJobsResponse | null>(null);
  const [options, setOptions] = useState<CstUploadOptions>(EMPTY_CST_UPLOAD_OPTIONS);
  /** Mapping drafts and names of the new layouts, keyed by layout signature. */
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [layoutNames, setLayoutNames] = useState<Record<string, string>>({});
  /** Signatures of saved layouts the uploader chose to re-map into the separate identifier columns. */
  const [remapped, setRemapped] = useState<Record<string, boolean>>({});

  const { data: customers, isLoading: customersLoading } = useQuery({
    queryKey: ['cst-reporting-customers'],
    queryFn: ({ signal }) => apiGet<ReportingCustomer[]>('/api/v1/imports/cst/reporting-customers', { signal }),
    enabled: open,
  });

  const resetPreview = useCallback(() => {
    setPreview(null);
    setResults(null);
    setDrafts({});
    setLayoutNames({});
    setRemapped({});
  }, []);

  const addFiles = useCallback(
    (list: FileList | File[] | null) => {
      if (!list) return;
      const incoming = Array.from(list).filter((f) => extOk(f.name));
      // N-0111: pre-fill the year from the file names or their folder (never confirmed for the uploader).
      const suggested = suggestYearFromNames(incoming.flatMap((f) => [f.name, f.webkitRelativePath ?? '']));
      if (suggested != null) {
        setOptions((o) => (o.year === '' ? { ...o, year: String(suggested), yearConfirmed: false } : o));
      }
      setFiles((prev) => {
        const names = new Set(prev.map((f) => f.name.toLowerCase()));
        const next = [...prev];
        for (const f of incoming) {
          if (!names.has(f.name.toLowerCase())) {
            next.push(f);
            names.add(f.name.toLowerCase());
          }
        }
        return next;
      });
      resetPreview();
    },
    [resetPreview]
  );

  const removeAt = useCallback(
    (idx: number) => {
      setFiles((prev) => prev.filter((_, i) => i !== idx));
      resetPreview();
    },
    [resetPreview]
  );

  const canPropose = customerId !== '' && files.length > 0;

  const propose = useMutation({
    mutationFn: async (): Promise<BatchProposeResponse> => {
      if (customerId === '') throw new Error('Pick the reporting customer first');
      const fd = new FormData();
      fd.append('customer_id', String(customerId));
      for (const file of files) fd.append('files', file);
      return apiPostFormData<BatchProposeResponse>('/api/v1/imports/cst/batch-propose', fd);
    },
    onSuccess: (data) => {
      setPreview(data);
      setResults(null);
      // Each distinct unmatched header set starts from what the parser detected (and the closest saved layout).
      const nextDrafts: Record<string, Record<string, string>> = {};
      const nextNames: Record<string, string> = {};
      for (const f of data.files ?? []) {
        if (!f.readable || f.layout || !f.layout_signature || nextDrafts[f.layout_signature]) continue;
        nextDrafts[f.layout_signature] = { ...f.detected_mapping };
        nextNames[f.layout_signature] = `${stem(f.filename)} layout`;
      }
      setDrafts(nextDrafts);
      setLayoutNames(nextNames);
    },
  });

  const newLayouts = useMemo<NewLayoutDraft[]>(() => {
    const bySig = new Map<string, NewLayoutDraft>();
    for (const f of preview?.files ?? []) {
      if (!f.readable || !f.layout_signature) continue;
      if (f.layout && !remapped[f.layout_signature]) continue;
      const cur = bySig.get(f.layout_signature);
      if (cur) cur.filenames.push(f.filename);
      else
        bySig.set(f.layout_signature, {
          signature: f.layout_signature,
          layoutId: f.layout?.id,
          filenames: [f.filename],
          columns: f.columns,
          samples: f.samples,
          similar: f.similar_layout ?? null,
        });
    }
    return [...bySig.values()];
  }, [preview, remapped]);

  /**
   * Saved layouts the files matched. Every one can be edited (its columns re-mapped); the ones that still
   * map the older single product column load as before and are offered a re-map into the separate slots.
   */
  const legacyLayouts = useMemo(() => {
    const bySig = new Map<
      string,
      { signature: string; name: string; mapping: Record<string, string>; filenames: string[]; legacy: boolean }
    >();
    for (const f of preview?.files ?? []) {
      if (!f.readable || !f.layout || !f.layout_signature) continue;
      const cur = bySig.get(f.layout_signature);
      if (cur) cur.filenames.push(f.filename);
      else
        bySig.set(f.layout_signature, {
          signature: f.layout_signature,
          name: f.layout.name,
          mapping: f.layout.mapping ?? {},
          filenames: [f.filename],
          legacy: !!f.layout.legacy_product_slot,
        });
    }
    return [...bySig.values()];
  }, [preview]);

  const mappingGaps = useMemo(
    () => newLayouts.flatMap((l) => missingGroups(drafts[l.signature] ?? {})),
    [newLayouts, drafts]
  );
  const readableCount = (preview?.files ?? []).filter((f) => f.readable).length;
  const canUpload = canPropose && preview != null && readableCount > 0 && mappingGaps.length === 0;

  const upload = useMutation({
    mutationFn: async (): Promise<BatchJobsResponse> => {
      if (customerId === '') throw new Error('Pick the reporting customer first');
      const fd = new FormData();
      fd.append('customer_id', String(customerId));
      for (const file of files) fd.append('files', file);
      if (newLayouts.length) {
        fd.append(
          'layouts',
          JSON.stringify(
            newLayouts.map((l) => ({
              signature: l.signature,
              ...(l.layoutId != null ? { layout_id: l.layoutId } : {}),
              name: (layoutNames[l.signature] ?? '').trim(),
              field_mapping: drafts[l.signature] ?? {},
            }))
          )
        );
      }
      appendCstUploadOptions(fd, options);
      fd.append('import_mode', importMode);
      return apiPostFormData<BatchJobsResponse>('/api/v1/imports/cst/batch-jobs', fd);
    },
    onSuccess: (data) => {
      setResults(data);
      const ids = data.jobs
        .filter((j) => j.outcome === 'created' && j.import_job_id != null)
        .map((j) => j.import_job_id as number);
      if (ids.length) onJobsCreated(ids);
      // Stay open when a file could not be placed, so the reason stays on screen.
      if (ids.length && !data.jobs.some((j) => j.outcome === 'error')) onClose();
    },
  });

  const targets = preview?.targets ?? [];
  /** The older single product column is offered for a layout only while that layout still maps it. */
  const targetsFor = (draft: Record<string, string>): CanonicalTargetOption[] =>
    Object.values(draft).includes(LEGACY_PRODUCT_TARGET)
      ? targets
      : targets.filter((t) => t.value !== LEGACY_PRODUCT_TARGET);
  const failed = (results?.jobs ?? []).filter((r) => r.outcome === 'error');

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="cst-bulk-upload-dialog">
      <DialogTitle>Upload customer sell-through</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Pick the reporting customer, then drop their files. Every file loads into the one sell-through table
            with its standard columns; the period is taken from each file&apos;s content. The first time a file
            has headers this customer has not used before, you map them once and the layout is saved for the next
            upload.
          </Typography>

          <FormControl size="small" sx={{ maxWidth: 420 }} disabled={customersLoading || upload.isPending}>
            <InputLabel id="cst-customer-label">Reporting customer</InputLabel>
            <Select
              labelId="cst-customer-label"
              label="Reporting customer"
              value={customerId}
              onChange={(e) => {
                setCustomerId(e.target.value === '' ? '' : Number(e.target.value));
                resetPreview();
              }}
              data-testid="cst-customer-select"
            >
              {(customers ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {!customersLoading && customers && customers.length === 0 ? (
            <Alert severity="warning">
              No customer is ticked as a reporting customer. Switch on Reports expected for a customer in CST steward → Key accounts &amp; feed profile.
            </Alert>
          ) : null}
          {customerId === '' ? null : <SavedLayouts customerId={customerId} />}

          <CstUploadOptionsFields
            value={options}
            onChange={setOptions}
            disabled={upload.isPending}
            testIdPrefix="cst-bulk"
          />

          <Box
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              addFiles(e.dataTransfer.files);
            }}
            sx={{ border: '1px dashed', borderColor: 'divider', borderRadius: 1, p: 2, textAlign: 'center' }}
            data-testid="cst-bulk-dropzone"
          >
            <CloudUploadOutlinedIcon color="action" sx={{ mb: 1 }} />
            <Typography variant="body2" gutterBottom>
              Drop CSV / XLSX files here, or choose files
            </Typography>
            <Button
              size="small"
              variant="outlined"
              onClick={() => inputRef.current?.click()}
              disabled={propose.isPending || upload.isPending}
            >
              Choose files
            </Button>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              hidden
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </Box>
          {files.length ? (
            <Table size="small" data-testid="cst-bulk-file-list">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell>Column layout</TableCell>
                  <TableCell width={80} />
                </TableRow>
              </TableHead>
              <TableBody>
                {files.map((f, i) => {
                  const info = preview?.files?.find((x) => x.filename === f.name);
                  return (
                    <TableRow key={`${f.name}-${i}`}>
                      <TableCell>{f.name}</TableCell>
                      <TableCell>
                        {!info ? (
                          '—'
                        ) : !info.readable ? (
                          <Chip size="small" color="error" variant="outlined" label="Cannot read this file" />
                        ) : info.layout ? (
                          <Chip
                            size="small"
                            color={info.layout.legacy_product_slot ? 'default' : 'success'}
                            variant="outlined"
                            label={`Layout: ${info.layout.name}${info.layout.legacy_product_slot ? ' (older product column)' : ''}`}
                          />
                        ) : (
                          <Chip size="small" color="warning" variant="outlined" label="New layout: map the columns" />
                        )}
                      </TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label={`remove ${f.name}`}
                          onClick={() => removeAt(i)}
                          disabled={propose.isPending || upload.isPending}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : null}
          {canPropose && !preview ? (
            <Button
              variant="outlined"
              onClick={() => void propose.mutateAsync()}
              disabled={propose.isPending}
              data-testid="cst-bulk-preview-groups"
            >
              Check column layouts
            </Button>
          ) : null}
          {propose.isPending ? <LinearProgress /> : null}
          {propose.isError ? <Alert severity="error">{safeDisplayError(propose.error)}</Alert> : null}

          {preview ? (
            <Stack spacing={2} data-testid="cst-bulk-group-preview">
              {(preview.files ?? [])
                .filter((f) => !f.readable)
                .map((f) => (
                  <Alert key={f.filename} severity="error">
                    {f.filename}: {f.unreadable_reason ?? 'could not be read'}. It will be skipped.
                  </Alert>
                ))}
              {newLayouts.length === 0 && readableCount > 0 ? (
                <Alert severity="success">
                  Every file matches a saved layout of this customer. Nothing to map.
                </Alert>
              ) : null}
              {legacyLayouts
                .filter((l) => !remapped[l.signature])
                .map((l) => (
                  <Alert
                    key={l.signature}
                    severity="info"
                    data-testid={l.legacy ? `cst-legacy-layout-${l.signature}` : `cst-saved-layout-${l.signature}`}
                    action={
                      <Button
                        size="small"
                        data-testid={`cst-remap-${l.signature}`}
                        onClick={() => {
                          setRemapped((p) => ({ ...p, [l.signature]: true }));
                          // Start from what the layout maps today; its older product column is left to re-map.
                          setDrafts((p) => ({ ...p, [l.signature]: { ...l.mapping } }));
                          setLayoutNames((p) => ({ ...p, [l.signature]: l.name }));
                        }}
                      >
                        {l.legacy ? 'Re-map product columns' : 'Edit column mapping'}
                      </Button>
                    }
                  >
                    {l.legacy
                      ? `Layout ${l.name} maps one product column that may hold any identifier. It keeps loading as before. You can re-map it into Part number, Barcode, Sales model and Customer product code.`
                      : `Layout ${l.name} is saved for this customer. Change how its columns are mapped, and the layout is updated.`}
                  </Alert>
                ))}
              {newLayouts.map((l) => {
                const gaps = missingGroups(drafts[l.signature] ?? {});
                return (
                  <Box
                    key={l.signature}
                    sx={{ border: 1, borderColor: gaps.length ? 'warning.main' : 'divider', borderRadius: 1, p: 1.5 }}
                    data-testid={`cst-new-layout-${l.signature}`}
                  >
                    <Stack spacing={1}>
                      <Typography variant="subtitle2">
                        {l.layoutId != null ? 'Re-map column layout' : 'New column layout'} · {l.filenames.length} file
                        {l.filenames.length === 1 ? '' : 's'}
                      </Typography>
                      <Stack direction="row" flexWrap="wrap" gap={0.5}>
                        {l.filenames.map((n) => (
                          <Chip key={n} size="small" variant="outlined" label={n} />
                        ))}
                      </Stack>
                      {l.similar ? (
                        <Typography variant="caption" color="text.secondary">
                          Started from the closest saved layout, {l.similar.name}. Check each column.
                        </Typography>
                      ) : null}
                      <TextField
                        size="small"
                        label="Layout name"
                        value={layoutNames[l.signature] ?? ''}
                        onChange={(e) => setLayoutNames((p) => ({ ...p, [l.signature]: e.target.value }))}
                        disabled={l.layoutId != null}
                        sx={{ maxWidth: 420 }}
                      />
                      <CanonicalColumnMappingPanel
                        testIdPrefix={`cst-map-${l.signature}`}
                        fileHeaders={l.columns}
                        draft={drafts[l.signature] ?? {}}
                        onChange={(next) => setDrafts((p) => ({ ...p, [l.signature]: next }))}
                        targetOptions={targetsFor(drafts[l.signature] ?? {})}
                        columnNotes={
                          l.layoutId != null
                            ? Object.fromEntries(
                                Object.entries(drafts[l.signature] ?? {})
                                  .filter(([, t]) => t === LEGACY_PRODUCT_TARGET)
                                  .map(([h]) => [
                                    h,
                                    'Older single product column. Re-map it to Part number, Barcode, Sales model or Customer product code.',
                                  ])
                              )
                            : undefined
                        }
                        columnSamples={l.samples}
                        requiredGroups={REQUIRED_GROUPS}
                        disabled={upload.isPending}
                      />
                    </Stack>
                  </Box>
                );
              })}
            </Stack>
          ) : null}

          {upload.isPending ? <LinearProgress /> : null}
          {upload.isError ? <Alert severity="error">{safeDisplayError(upload.error)}</Alert> : null}
          {failed.map((r, i) => (
            <Alert severity="error" key={i} data-testid="cst-bulk-error">
              {r.filenames.join(', ')}: {r.error}
            </Alert>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={upload.isPending}>
          Close
        </Button>
        <Button
          variant="contained"
          disabled={!canUpload || upload.isPending || propose.isPending}
          onClick={() => void upload.mutateAsync()}
          startIcon={upload.isPending ? <CircularProgress size={16} /> : undefined}
          data-testid="cst-bulk-upload-submit"
        >
          Upload files
        </Button>
      </DialogActions>
    </Dialog>
  );
}

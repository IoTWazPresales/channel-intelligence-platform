'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  InputAdornment,
  InputLabel,
  LinearProgress,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Step,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import Link from '@mui/material/Link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef, GridApi, GridOptions } from 'ag-grid-community';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { BulkSelectionToolbar } from '@/components/bulkTable/BulkSelectionToolbar';
import {
  ImportJobBulkDeleteImpactDialog,
  type ImportJobBulkDeletePreview,
} from '@/components/bulkTable/ImportJobBulkDeleteImpactDialog';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { ShipmentEntityStewardPanel } from '@/app/(app)/admin/shipment-evidence/ShipmentEntityStewardPanel';
import { apiGet, apiPost, apiUrl, readFetchError, safeDisplayError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import { PmImportProgressPanel, type PmProgressSnapshot } from './PmImportProgressPanel';
import { DsiImportJobResolutionSection } from './DsiImportJobResolutionSection';
import type { DsiCandidateRow } from '../mappings/DsiCandidateStewardPanel';
import {
  dsiContinueToApplyAllowed,
  dsiGateFromMapping,
  dsiSelectValue,
  dsiTargetDescription,
  dsiTargetLabel,
  formatDsiSamples,
  parseDistributorSiSummaryFromRows,
  stableFieldMappingJson,
} from './dsiStepUtils';
import {
  initPmColumnDrafts,
  PM_GROUP_LABEL,
  pmDraftsToApiColumns,
  sortPmFieldDefinitions,
  type PmColumnDraft,
  type PmDisposition,
  type PmFieldDefinition,
} from './pmMappingHelpers';
import {
  buildTargetUsageMap,
  enrichPmMappingTargets,
  filterAndSortPmTargets,
  type EnrichedPmTargetOption,
} from './pmMappingTargetOptions';

type ImportTemplate = {
  id: number;
  slug: string;
  display_name: string;
  description: string | null;
  requires_provider: boolean;
  accepted_file_types: string[];
  required_fields: string[];
  optional_fields: string[];
  pipeline_ready: boolean;
  destructive_apply_requires_confirm: boolean;
};

type Source = {
  id: number;
  code: string;
  name: string;
  import_template_slug: string | null;
};

type Job = {
  id: number;
  status: string;
  stage: string;
  file_name: string;
  error_summary: string | null;
  template_slug?: string | null;
  import_mode?: string | null;
  archived_at?: string | null;
};

type RowResult = {
  id: number;
  row_number: number;
  severity: string;
  code: string;
  message: string;
  raw_payload?: Record<string, unknown> | null;
};

type GenericUploadArgs = {
  file: File;
  modeOverride?: 'validate' | 'apply';
  mappingOverride?: Record<string, Record<string, string>>;
};

type HlSheetDetail = {
  sheet_name: string;
  header_row_number: number;
  mapped_fields: string[];
  source_columns: string[];
  row_count: number;
  mapping_confidence: number;
};

type LineupLine = {
  id: number;
  header_id: number;
  source_row_number: number;
  product_id: number | null;
  sku_raw: string | null;
  part_number_raw: string | null;
  model_raw: string | null;
  base_unit_raw: string | null;
  quantity_units: number | null;
  msrp_local: number | null;
  promo_price_local: number | null;
  dap_local: number | null;
  disti_margin_pct: number | null;
  period_label: string | null;
  header_customer_id: number | null;
  sheet_name: string;
  // Resolution status — read-only audit surface from persisted line records.
  diagnostic_codes: string[];
  customer_token: string | null;
};

type HlJobDetail = {
  id: number;
  status: string;
  stage: string;
  field_mapping?: Record<string, Record<string, string>> | null;
  inferred_schema?: { selected_sheet_details?: HlSheetDetail[] } | null;
};

type InferredColumn = { name: string; dtype: string; sample: unknown[] };

type PmSuggestionDetail = {
  target?: string;
  suggested_target?: string;
  mapper_action?: string;
  recommended_disposition?: 'stage_raw' | 'ignore';
  from_source_memory?: boolean;
  disposition?: string;
  confidence?: number;
  reasons?: string[];
  runner_up?: { target?: string; confidence?: number; reasons?: string[] } | null;
  hint_target?: string;
};

type PmJobState = {
  id: number;
  stage: string;
  status: string;
  file_name: string;
  file_headers: string[];
  suggested_mapping: Record<string, PmSuggestionDetail> | null;
  mapping_decisions: Record<string, { target?: string; disposition?: string }> | null;
  canonical_fields: string[];
  required_fields: string[];
  identity_targets?: string[];
  identity_rule?: string;
  field_definitions?: PmFieldDefinition[];
  validation_passed: boolean | null;
  error_summary: string | null;
  staged_metadata_preview: Record<string, Record<string, unknown>> | null;
  /** Present after infer; includes dtype + first-row samples per column (JSON-safe). */
  inferred_schema?: { row_count: number; columns: InferredColumn[] } | null;
  /** Server-derived progress (counts, rail, phase); refreshed while validate/commit run. */
  progress?: PmProgressSnapshot | null;
};

const HL_MAPPING_DISPLAY_FIELDS: Array<{ canonical: string; label: string }> = [
  { canonical: 'customer_token', label: 'Customer' },
  { canonical: 'distributor_token', label: 'Distributor' },
  { canonical: 'sku_raw', label: 'Product identity (SKU)' },
  { canonical: 'part_number_raw', label: 'Part number' },
  { canonical: 'model_raw', label: 'Model name' },
  { canonical: 'base_unit_raw', label: 'Base unit (descriptor)' },
  { canonical: 'quantity_units', label: 'Quantity' },
  { canonical: 'period_label', label: 'Period / month' },
  { canonical: 'msrp_local', label: 'MSRP / list price' },
];

// Diagnostic codes shown as error-colored chips in the summary bar.
const HL_DIAGNOSTIC_ERROR_CODES = new Set([
  'unknown_product',
  'unknown_customer',
  'missing_key_fields',
  'invalid_quantity',
  'ambiguous_product_match',
  'ambiguous_customer_match',
  'unknown_distributor',
]);

// Codes that hard-block apply (row data is unresolvable without intervention).
// unknown_customer is intentionally excluded: rows can still be saved with a null
// customer FK and resolved in a later mapping step.
const HL_APPLY_BLOCKING_CODES = new Set([
  'unknown_product',
  'missing_key_fields',
  'invalid_quantity',
  'ambiguous_product_match',
  'ambiguous_customer_match',
]);

const stepsDefault = ['Import type', 'Data provider', 'Template details', 'Import mode', 'Upload & preview'];

const stepsShipmentEvidence = ['Import type', 'Data provider', 'Template details', 'Upload & preview'];

const stepsPm = [
  'Import type',
  'Data provider',
  'Template details',
  'Upload file',
  'Column mapping',
  'Validate results',
  'Commit to catalog',
];

const stepsDsi = [
  'Import type',
  'Data provider',
  'Template details',
  'Import mode',
  'Upload file',
  'Column mapping',
  'Validate',
  'Apply',
];

const defaultHeaders = { 'X-User-Role': 'admin', 'X-User-Id': 'demo-user' };
const DEFERRED_TEMPLATE_SLUGS = new Set(['customer_channel_mapping']);

/** Human labels for inbound shipment canonical mapping targets (imports column-mapping step). */
const SHIPMENT_FIELD_LABELS: Record<string, string> = {
  operating_unit: 'Operating unit',
  bill_to_raw: 'Bill To (distributor token)',
  ship_to_raw: 'Ship To (distributor token)',
  distributor_token: 'Distributor',
  order_no: 'Order no.',
  order_line: 'Order line',
  delivery_no: 'Delivery no.',
  invoice_line: 'Invoice line',
  item_code: 'Item / SKU code',
  sales_model_name: 'Sales model name',
  customer_item: 'Customer item',
  ean_code: 'EAN',
  upc_code: 'UPC',
  mpor_item_no: 'MPOR item no.',
  quantity: 'Quantity',
  unit_price: 'Unit price',
  amount: 'Amount',
  currency_code: 'Currency',
  ship_confirm_date: 'Ship confirm date',
  schedule_ship_date: 'Schedule ship date',
  promise_date: 'Promise date',
  exwork_date: 'Ex-work date',
  erd_date: 'ERD (est. revenue date)',
  est_pod_date: 'Est. POD date (expected delivery)',
  pod_date: 'POD date (actual delivery)',
  customer_dealer_token: 'Source customer name',
};

function describeTemplateBehavior(template: ImportTemplate | null, isPm: boolean, isDsi: boolean): string {
  if (!template) return 'Pipeline behavior is determined by the selected import type and provider.';
  if (isPm) {
    return 'You upload a file, map columns only to approved Product Master fields, validate rows, then commit. Extra columns can be ignored or retained as staged metadata (no new schema from this UI).';
  }
  if (isDsi) {
    return (
      'Source files may use your own column names (for example DISTI for distributor). After upload, map each column to ' +
      'the required business fields; the system auto-suggests matches and remembers mappings for this provider. ' +
      'Validate previews staging and diagnostics, then apply to upsert canonical sell-out and inventory facts. ' +
      'Master products, customers, and distributors are never auto-created from this import.'
    );
  }
  if (!template.pipeline_ready) {
    return 'File is stored and schema inferred; full loader for this type is not enabled yet.';
  }
  switch (template.slug) {
    case 'distributor_master':
      return 'Validates distributor_code/distributor_name, then upserts dim_distributor when mode is Apply.';
    case 'customer_master':
      return 'Validates customer master fields, then upserts dim_customer when mode is Apply.';
    case 'inbound_shipments':
      return (
        'Runs in validate mode: after upload, confirm column mapping (auto-suggested), then run validation to write ' +
        'shipment evidence lines. Use Shipment evidence admin to steward entities and Apply when ready.'
      );
    default:
      return 'Runs the configured template pipeline for this import type.';
  }
}

function formatPmSamples(samples: unknown[] | undefined): string {
  if (!samples?.length) return '—';
  const parts = samples
    .map((s) => {
      if (s === null || s === undefined) return '';
      const str = String(s);
      return str.length > 48 ? `${str.slice(0, 45)}…` : str;
    })
    .filter((x) => x.length > 0);
  return parts.length ? parts.join(' · ') : '—';
}

const PM_SUGGEST_REASON_LABELS: Record<string, string> = {
  deterministic_alias_header: 'Universal column match (industry terms)',
  deterministic_value_evidence: 'Sample values match this field type',
  exact_header_match: 'Exact field key match',
  normalized_header_match: 'Normalized header matches field',
  legacy_alias_header: 'Known legacy column alias',
  alias_catalog_match: 'Alias catalog match',
  import_template_mapping: 'Import template mapping',
  template_mapping: 'Import template default',
  header_keyword_signal: 'Header keyword signal',
  sample_values_resemble_form_factor: 'Samples look like form factor',
  sample_values_resemble_platform_cpu_family: 'Samples look like platform / CPU family',
  sample_values_resemble_series_or_segment_name: 'Samples look like series / segment',
  sample_values_resemble_barcode: 'Samples look like a barcode (legacy signal)',
  sample_values_resemble_technical_id: 'Samples look like a technical id (legacy signal)',
  sample_values_resemble_long_title: 'Samples look like a long title',
  barcode_like_value: 'Values look like a strict GTIN/UPC',
  technical_id_like_value: 'Values look like a technical / part code',
  date_like_value: 'Date-like values and date role',
  dtype_numeric_capacity_like: 'Numeric / capacity-like values',
  semantic_group_aligned_with_header: 'Semantic group matches header',
  semantic_group_mismatch_penalty: 'Semantic group mismatch (down-ranked)',
  low_confidence: 'Low confidence',
  ambiguous_close_runner_up: 'Ambiguous — close alternative',
  target_already_used: 'Target already mapped by another column',
  identity_target_already_mapped: 'Identity field already mapped',
  alias_match: 'Generic industry alias',
  source_memory: 'Learned from previous imports for this source',
  no_suitable_canonical_target: 'No suitable core field in this model',
  recommend_stage_metadata: 'Recommended: keep as staged metadata',
  recommend_ignore: 'Recommended: ignore for Product Master',
  identifier_resolution_available: 'Optional identifier resolution (if configured)',
};

function formatPmSuggestReason(code: string): string {
  return PM_SUGGEST_REASON_LABELS[code] ?? code.replace(/_/g, ' ');
}

function AdminImportsPageContent() {
  const qc = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeStep, setActiveStep] = useState(0);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | ''>('');
  const [importMode, setImportMode] = useState<'validate' | 'apply'>('validate');
  const [confirmDestructive, setConfirmDestructive] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [lastJobId, setLastJobId] = useState<number | null>(null);
  const [lastGenericFile, setLastGenericFile] = useState<File | null>(null);
  const [historicalValidatedJobId, setHistoricalValidatedJobId] = useState<number | null>(null);
  const [isJobRevisitMode, setIsJobRevisitMode] = useState(false);
  const [hlMappingEdits, setHlMappingEdits] = useState<Record<string, Record<string, string>>>({});
  const [showMappingReview, setShowMappingReview] = useState(false);
  const [hlShowApplyConfirm, setHlShowApplyConfirm] = useState(false);
  const [lastApplyJobId, setLastApplyJobId] = useState<number | null>(null);
  const [pmColumns, setPmColumns] = useState<PmColumnDraft[]>([]);
  const [pmRowFilter, setPmRowFilter] = useState<'all' | 'unmapped' | 'mapped' | 'core'>('all');
  const [pmBulkSelected, setPmBulkSelected] = useState<Record<string, boolean>>({});
  const [dsiMapDraft, setDsiMapDraft] = useState<Record<string, string>>({});
  const [jobsBulkSelectionMode, setJobsBulkSelectionMode] = useState<'normal' | 'selecting'>('normal');
  const [jobsSelectedCount, setJobsSelectedCount] = useState(0);
  const [jobsVisibleRowCount, setJobsVisibleRowCount] = useState(0);
  const [showArchivedImportJobs, setShowArchivedImportJobs] = useState(false);
  const jobsGridApiRef = useRef<GridApi<Job> | null>(null);
  const [importJobBulkDeleteOpen, setImportJobBulkDeleteOpen] = useState(false);
  const [importJobBulkDeletePreview, setImportJobBulkDeletePreview] = useState<ImportJobBulkDeletePreview | null>(null);
  const [importJobBulkDeleteBusy, setImportJobBulkDeleteBusy] = useState(false);
  const [importJobDeleteSemanticArtifacts, setImportJobDeleteSemanticArtifacts] = useState(false);
  const [importJobBulkDeleteAck, setImportJobBulkDeleteAck] = useState(false);
  const [shipmentApplyWarning, setShipmentApplyWarning] = useState<string | null>(null);
  const [shipmentMapDraft, setShipmentMapDraft] = useState<Record<string, string>>({});

  const jobIdParam = useMemo(() => {
    const v = searchParams.get('job');
    return v && !Number.isNaN(Number(v)) ? Number(v) : null;
  }, [searchParams]);

  const isPm = selectedSlug === 'product_master';
  const isDsi = selectedSlug === 'distributor_inventory';
  const isShipmentEvidence = selectedSlug === 'inbound_shipments';
  const steps = isPm ? stepsPm : isDsi ? stepsDsi : isShipmentEvidence ? stepsShipmentEvidence : stepsDefault;
  const { data: templates } = useQuery({
    queryKey: ['import-templates'],
    queryFn: ({ signal }) => apiGet<ImportTemplate[]>('/api/v1/imports/templates', { signal }),
  });
  const visibleTemplates = useMemo(
    () => (templates ?? []).filter((t) => !DEFERRED_TEMPLATE_SLUGS.has(t.slug)),
    [templates]
  );

  const selectedTemplate = useMemo(
    () => visibleTemplates.find((t) => t.slug === selectedSlug) ?? null,
    [visibleTemplates, selectedSlug]
  );

  useEffect(() => {
    if (!visibleTemplates.length) return;
    const forcedTemplate = searchParams.get('template');
    if (!forcedTemplate) return;
    const exists = visibleTemplates.some((t) => t.slug === forcedTemplate);
    if (!exists) return;
    setSelectedSlug(forcedTemplate);
    setSourceId('');
    setImportMode(
      forcedTemplate === 'product_master' ||
        forcedTemplate === 'historical_lineup' ||
        forcedTemplate === 'distributor_inventory' ||
        forcedTemplate === 'inbound_shipments'
        ? 'validate'
        : 'apply'
    );
    setConfirmDestructive(false);
    setLastGenericFile(null);
    setHistoricalValidatedJobId(null);
    setIsJobRevisitMode(false);
    setActiveStep(1);
  }, [visibleTemplates, searchParams]);

  const { data: sources } = useQuery({
    queryKey: ['import-sources', selectedSlug],
    queryFn: ({ signal }) =>
      apiGet<Source[]>(`/api/v1/imports/sources?template_slug=${encodeURIComponent(selectedSlug!)}`, { signal }),
    enabled: !!selectedSlug,
  });

  useEffect(() => {
    if (!sources?.length) return;
    const forcedSource = searchParams.get('source');
    if (!forcedSource) return;
    const id = Number(forcedSource);
    if (!Number.isFinite(id)) return;
    if (!sources.some((s) => s.id === id)) return;
    setSourceId(id);
  }, [sources, searchParams]);

  const {
    data: jobs,
    isLoading: jobsLoading,
    isError: jobsIsError,
    error: jobsErr,
    refetch: refetchJobs,
  } = useQuery({
    queryKey: ['import-jobs', showArchivedImportJobs],
    queryFn: ({ signal }) =>
      apiGet<Job[]>(
        showArchivedImportJobs
          ? '/api/v1/imports/jobs?include_archived=true'
          : '/api/v1/imports/jobs',
        { signal },
      ),
  });

  const { data: previewRows, refetch: refetchPreview } = useQuery({
    queryKey: ['import-job-rows', lastJobId],
    queryFn: ({ signal }) => apiGet<RowResult[]>(`/api/v1/imports/jobs/${lastJobId}/rows`, { signal }),
    enabled: lastJobId != null,
  });

  const { data: jobDetail } = useQuery({
    queryKey: ['import-job', jobIdParam],
    queryFn: ({ signal }) => apiGet<Job>(`/api/v1/imports/jobs/${jobIdParam}`, { signal }),
    enabled: jobIdParam != null,
  });

  // Fetch job detail for historical_lineup validate job to power the mapping review panel.
  const { data: hlJobDetail } = useQuery({
    queryKey: ['import-job', historicalValidatedJobId],
    queryFn: ({ signal }) =>
      apiGet<HlJobDetail>(`/api/v1/imports/jobs/${historicalValidatedJobId}`, { signal }),
    enabled: historicalValidatedJobId != null && selectedSlug === 'historical_lineup',
  });

  // Derive the apply job ID: either from a just-completed apply in this session, or from
  // a revisited apply-mode job via ?job=.  Used to fetch and display loaded lineup lines.
  const hlApplyJobId: number | null =
    lastApplyJobId ??
    (isJobRevisitMode && selectedSlug === 'historical_lineup' && jobDetail?.import_mode === 'apply'
      ? (jobDetail.id ?? null)
      : null);

  const { data: lineupLines } = useQuery({
    queryKey: ['lineup-lines', hlApplyJobId],
    queryFn: ({ signal }) =>
      apiGet<LineupLine[]>(`/api/v1/imports/jobs/${hlApplyJobId}/lineup-lines`, { signal }),
    enabled: hlApplyJobId != null && selectedSlug === 'historical_lineup',
  });

  // Group unresolved customer tokens from persisted line records — read-only audit surface.
  // No customer_id mutation occurs here; this is purely derived from what was written on apply.
  const unresolvedCustomerTokens = useMemo<Map<string, number>>(() => {
    if (!lineupLines?.length) return new Map();
    const counts = new Map<string, number>();
    for (const ln of lineupLines) {
      if (ln.diagnostic_codes.includes('unknown_customer') && ln.customer_token) {
        counts.set(ln.customer_token, (counts.get(ln.customer_token) ?? 0) + 1);
      }
    }
    return counts;
  }, [lineupLines]);

  // Sync ?job=<id> URL param into wizard state so previous job diagnostics are visible after refresh.
  // Guards: skip if ?template= is driving a new import flow; skip until templates have loaded.
  useEffect(() => {
    if (searchParams.get('template')) return;
    if (!jobDetail || !visibleTemplates.length) return;
    setLastJobId(jobDetail.id);
    setSelectedSlug(jobDetail.template_slug ?? null);
    setIsJobRevisitMode(true);
    if (jobDetail.template_slug !== 'product_master') {
      if (jobDetail.template_slug === 'distributor_inventory' && jobDetail.stage === 'dsi_mapping_ready') {
        setActiveStep(5);
      } else if (jobDetail.template_slug === 'inbound_shipments') {
        setActiveStep(3);
      } else {
        setActiveStep(4);
      }
    }
    // PM jobs: activeStep stays at 0; a deferred alert is shown instead of
    // attempting to reconstruct the PM mapping/validate/commit wizard.
  }, [jobDetail, visibleTemplates, searchParams]);

  // Diagnostic summary: group previewRows by code, sorted by count desc, capped at 8.
  const diagnosticSummary = useMemo<Array<{ code: string; count: number }>>(() => {
    if (!previewRows?.length) return [];
    const counts: Record<string, number> = {};
    for (const r of previewRows) {
      if (r.code) counts[r.code] = (counts[r.code] ?? 0) + 1;
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([code, count]) => ({ code, count }));
  }, [previewRows]);

  // Quality Review: aggregate previewRows into blocking / warning / ok counts and tokens.
  // Active only for historical_lineup flows so the operator can assess apply readiness.
  const qualityReview = useMemo(() => {
    if (selectedSlug !== 'historical_lineup' || !previewRows?.length) return null;
    let blockingCount = 0;
    let okCount = 0;
    let commercialWarningCount = 0;
    const unknownCustomerTokens = new Map<string, number>();
    const invalidNumericExamples: string[] = [];

    for (const r of previewRows) {
      if (HL_APPLY_BLOCKING_CODES.has(r.code)) {
        blockingCount++;
      } else if (r.code === 'historical_lineup_row_ok') {
        okCount++;
      } else if (r.code === 'partial_margin_stack' || r.code === 'invalid_numeric') {
        commercialWarningCount++;
      }
      if (r.code === 'unknown_customer') {
        const token = (r.raw_payload?.customer_token as string | undefined) ?? '(unknown)';
        unknownCustomerTokens.set(token, (unknownCustomerTokens.get(token) ?? 0) + 1);
      }
      if (r.code === 'invalid_numeric' && invalidNumericExamples.length < 3) {
        const fields = r.raw_payload?._invalid_numeric_fields as string[] | undefined;
        if (fields?.length) {
          invalidNumericExamples.push(`row ${r.row_number}: ${fields.join(', ')}`);
        }
      }
    }

    const unknownCustomerRowCount = Array.from(unknownCustomerTokens.values()).reduce((a, b) => a + b, 0);
    return {
      blockingCount,
      okCount,
      commercialWarningCount,
      unknownCustomerTokens,
      unknownCustomerRowCount,
      unknownCustomerCount: unknownCustomerTokens.size,
      invalidNumericExamples,
      isApplyReady: blockingCount === 0,
    };
  }, [previewRows, selectedSlug]);

  const distributorSiSummary = useMemo(() => {
    if (selectedSlug !== 'distributor_inventory') return null;
    return parseDistributorSiSummaryFromRows(previewRows);
  }, [previewRows, selectedSlug]);

  const { data: dsiCandidates } = useQuery({
    queryKey: ['distributor-si-candidates', lastJobId],
    queryFn: ({ signal }) =>
      apiGet<DsiCandidateRow[]>(`/api/v1/mappings/import-jobs/${lastJobId}/distributor-si-candidates`, { signal }),
    enabled: lastJobId != null && selectedSlug === 'distributor_inventory',
  });

  type DsiMappingState = {
    id: number;
    stage: string;
    status: string;
    error_summary?: string | null;
    file_headers: string[];
    field_mapping: Record<string, string>;
    canonical_targets: string[];
    blocking_mapping_errors: Array<{ code: string; message: string }>;
    mapping_valid: boolean;
    column_samples?: Record<string, string[]>;
    mapping_adjustment_notices?: Array<{ code: string; message: string }>;
  };

  const { data: dsiMappingState, refetch: refetchDsiMapping } = useQuery({
    queryKey: ['dsi-mapping-state', lastJobId],
    queryFn: ({ signal }) =>
      apiGet<DsiMappingState>(`/api/v1/imports/jobs/${lastJobId}/dsi-mapping-state`, { signal }),
    enabled: Boolean(isDsi && lastJobId != null && activeStep >= 5),
  });

  const dsiServerMappingGateOk = useMemo(
    () => dsiGateFromMapping(dsiMappingState?.field_mapping ?? {}),
    [dsiMappingState?.field_mapping]
  );

  const dsiCanonSet = useMemo(
    () => new Set(dsiMappingState?.canonical_targets ?? []),
    [dsiMappingState?.canonical_targets]
  );

  const dsiServerMappingKey = useMemo(
    () => stableFieldMappingJson(dsiMappingState?.field_mapping),
    [dsiMappingState?.field_mapping]
  );

  const [dsiContinueGateKey, setDsiContinueGateKey] = useState<string | null>(null);
  const dsiMappingStateRef = useRef(dsiMappingState);
  dsiMappingStateRef.current = dsiMappingState;
  const lastJobIdRef = useRef(lastJobId);
  lastJobIdRef.current = lastJobId;

  useEffect(() => {
    if (!isDsi) return;
    setDsiMapDraft({});
    setDsiContinueGateKey(null);
  }, [isDsi, lastJobId]);

  const dsiMappingDraftDirty = useMemo(() => {
    if (!isDsi || !dsiMappingState?.file_headers?.length) return false;
    const server = dsiMappingState.field_mapping ?? {};
    for (const h of dsiMappingState.file_headers) {
      if ((dsiMapDraft[h] ?? '') !== (server[h] ?? '')) return true;
    }
    for (const k of Object.keys(dsiMapDraft)) {
      if (!dsiMappingState.file_headers.includes(k) && dsiMapDraft[k]) return true;
    }
    return false;
  }, [isDsi, dsiMapDraft, dsiMappingState?.field_mapping, dsiMappingState?.file_headers]);

  useEffect(() => {
    if (!isDsi || activeStep !== 5 || !dsiMappingState?.file_headers?.length) return;
    const server = dsiMappingState.field_mapping ?? {};
    const next: Record<string, string> = {};
    for (const h of dsiMappingState.file_headers) {
      const v = server[h];
      if (v && dsiCanonSet.has(v)) next[h] = v;
    }
    setDsiMapDraft(next);
  }, [isDsi, activeStep, dsiMappingState?.id, dsiServerMappingKey, dsiMappingState?.file_headers, dsiCanonSet]);

  const saveDsiMapping = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${lastJobId}/dsi-field-mapping`), {
        method: 'PUT',
        headers: { ...defaultHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ field_mapping: dsiMapDraft }),
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<DsiMappingState>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', lastJobId] });
      setDsiContinueGateKey(null);
    },
  });

  const dsiValidate = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${lastJobId}/dsi-validate`), {
        method: 'POST',
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<DsiMappingState>;
    },
    onSuccess: async () => {
      const jid = lastJobIdRef.current;
      void qc.invalidateQueries({ queryKey: ['import-job-rows', jid] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', jid] });
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', jid] });
      const { data: rows } = await refetchPreview();
      await refetchDsiMapping();
      const summ = parseDistributorSiSummaryFromRows(rows ?? undefined);
      const fm = dsiMappingStateRef.current?.field_mapping ?? {};
      const key = `${jid ?? ''}::${stableFieldMappingJson(fm)}`;
      if (summ && (summ.blocking_rows ?? 0) === 0) {
        setDsiContinueGateKey(key);
      } else {
        setDsiContinueGateKey(null);
      }
    },
    onError: () => {
      setDsiContinueGateKey(null);
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });

  useEffect(() => {
    dsiValidate.reset();
  }, [lastJobId]);

  const dsiApply = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const fd = new FormData();
      const cd =
        !selectedTemplate?.destructive_apply_requires_confirm ||
        (selectedTemplate.destructive_apply_requires_confirm && confirmDestructive);
      fd.append('confirm_destructive', cd ? 'true' : 'false');
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${lastJobId}/dsi-apply`), {
        method: 'POST',
        body: fd,
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<DsiMappingState>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
    onError: () => {
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });

  const dsiCanContinueToApply = useMemo(
    () =>
      dsiContinueToApplyAllowed(dsiContinueGateKey, lastJobId, dsiMappingState?.field_mapping, distributorSiSummary, {
        isValidating: dsiValidate.isPending,
        hasServerGate: dsiServerMappingGateOk,
      }),
    [
      dsiContinueGateKey,
      lastJobId,
      dsiMappingState?.field_mapping,
      distributorSiSummary,
      dsiValidate.isPending,
      dsiServerMappingGateOk,
    ]
  );

  const dsiHasValidateResult = Boolean(distributorSiSummary) || dsiValidate.isSuccess || dsiValidate.isError;

  useEffect(() => {
    if (!isDsi || !dsiMappingDraftDirty) return;
    setDsiContinueGateKey(null);
    dsiValidate.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when draft diverges from saved server mapping
  }, [isDsi, dsiMappingDraftDirty]);

  const dsiGateOk = useMemo(() => dsiGateFromMapping(dsiMapDraft), [dsiMapDraft]);

  const dsiJobFailedAlert =
    isDsi && dsiMappingState?.status === 'failed' && dsiMappingState.error_summary ? (
      <Alert severity="error" data-testid="dsi-job-failed-banner">
        Import job failed: {dsiMappingState.error_summary}
      </Alert>
    ) : null;

  // Derived data for the HL mapping review panel.
  const hlSheetDetail: HlSheetDetail | null =
    hlJobDetail?.inferred_schema?.selected_sheet_details?.[0] ?? null;
  const hlDetectedMapping: Record<string, string> =
    hlSheetDetail ? (hlJobDetail?.field_mapping?.[hlSheetDetail.sheet_name] ?? {}) : {};
  const hlSourceColumns: string[] = hlSheetDetail?.source_columns ?? [];
  const hlHasEdits = Object.values(hlMappingEdits).some((m) => Object.keys(m).length > 0);

  const upload = useMutation({
    mutationFn: async ({ file, modeOverride, mappingOverride }: GenericUploadArgs) => {
      if (selectedTemplate?.requires_provider && sourceId === '')
        throw new Error('Select a data provider before uploading.');
      const fd = new FormData();
      const effectiveMode =
        selectedSlug === 'inbound_shipments'
          ? 'validate'
          : modeOverride ?? importMode;
      fd.append('source_id', String(sourceId));
      fd.append('file', file);
      fd.append('run_sync', selectedSlug === 'distributor_inventory' ? 'false' : 'true');
      fd.append('import_mode', effectiveMode);
      if (selectedTemplate?.destructive_apply_requires_confirm && effectiveMode === 'apply') {
        fd.append('confirm_destructive', confirmDestructive ? 'true' : 'false');
      }
      if (mappingOverride && Object.keys(mappingOverride).length > 0) {
        fd.append('mapping_override', JSON.stringify(mappingOverride));
      }
      const res = await fetch(apiUrl('/api/v1/imports/jobs'), {
        method: 'POST',
        body: fd,
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<{ id: number; status: string; stage: string; import_mode: 'validate' | 'apply' }>;
    },
    onSuccess: (data) => {
      setLastJobId(data.id);
      if (selectedSlug === 'inbound_shipments') {
        setShipmentApplyWarning(null);
      }
      if (selectedSlug === 'historical_lineup' && data.import_mode === 'validate') {
        setHistoricalValidatedJobId(data.id);
        setHlMappingEdits({});
        setShowMappingReview(false);
      } else if (selectedSlug === 'historical_lineup' && data.import_mode === 'apply') {
        // Apply completed — clear button gate so Apply button disappears immediately.
        setHistoricalValidatedJobId(null);
        setLastGenericFile(null);
        setHlMappingEdits({});
        setShowMappingReview(false);
        setHlShowApplyConfirm(false);
        setLastApplyJobId(data.id);
      }
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', data.id] });
      void qc.invalidateQueries({ queryKey: ['import-job', data.id] });
      void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', data.id] });
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', data.id] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', data.id] });
      if (selectedSlug === 'distributor_inventory') {
        setActiveStep(5);
      }
    },
  });

  /** Inbound shipments job is identifiable from `?job=` detail before `lastJobId` sync (avoids race with `lastJobId`). */
  const shipmentEvidenceUrlUnlock =
    jobIdParam != null && jobDetail?.template_slug === 'inbound_shipments';

  const shipmentEvidenceJobPollUnlocked = upload.isSuccess || shipmentEvidenceUrlUnlock;

  /** Prefer post-upload `lastJobId` when it wins over a stale `?job=`; else URL id when detail confirms inbound; else wizard job. */
  const shipmentEvidencePollJobId =
    upload.isSuccess && isShipmentEvidence && lastJobId != null
      ? lastJobId
      : shipmentEvidenceUrlUnlock && jobIdParam != null
        ? jobIdParam
        : isShipmentEvidence && lastJobId != null
          ? lastJobId
          : null;

  const { data: shipmentImportJob } = useQuery({
    queryKey: ['import-job', shipmentEvidencePollJobId],
    queryFn: ({ signal }) => apiGet<Job>(`/api/v1/imports/jobs/${shipmentEvidencePollJobId!}`, { signal }),
    enabled: Boolean(shipmentEvidenceJobPollUnlocked && shipmentEvidencePollJobId != null),
    refetchInterval: (q) => {
      const j = q.state.data;
      if (!j) return 1500;
      const st = (j.stage || '').trim();
      if (st === 'validated' || st === 'loaded' || st === 'failed' || st === 'shipment_mapping_ready') return false;
      return 1500;
    },
  });

  /** Job id for shipment column mapping + validate (matches steward poll id). */
  const shipmentMappingJobId: number | null = shipmentEvidencePollJobId ?? lastJobId ?? null;

  type ShipmentMappingState = {
    id: number;
    stage: string;
    status: string;
    error_summary?: string | null;
    file_headers: string[];
    field_mapping: Record<string, string>;
    canonical_targets: string[];
    blocking_mapping_errors: Array<{ code: string; message: string }>;
    mapping_valid: boolean;
    mapping_adjustment_notices?: Array<{ code?: string; message?: string }>;
    column_samples?: Record<string, string[]>;
    field_target_descriptions?: Record<string, string>;
  };

  const {
    data: shipmentMappingState,
    isLoading: shipmentMappingStateLoading,
    isError: shipmentMappingStateQueryError,
    error: shipmentMappingStateQueryErr,
  } = useQuery({
    queryKey: ['shipment-mapping-state', shipmentMappingJobId],
    queryFn: ({ signal }) =>
      apiGet<ShipmentMappingState>(`/api/v1/imports/jobs/${shipmentMappingJobId}/shipment-mapping-state`, { signal }),
    enabled: Boolean(
      isShipmentEvidence &&
        shipmentMappingJobId != null &&
        shipmentImportJob &&
        (shipmentImportJob.stage || '').trim() === 'shipment_mapping_ready'
    ),
  });

  const shipmentCanonSet = useMemo(
    () => new Set(shipmentMappingState?.canonical_targets ?? []),
    [shipmentMappingState?.canonical_targets]
  );

  useEffect(() => {
    if (!isShipmentEvidence) {
      setShipmentMapDraft({});
    }
  }, [isShipmentEvidence, shipmentMappingJobId]);

  useEffect(() => {
    if (!isShipmentEvidence || !shipmentMappingState?.file_headers?.length) return;
    const server = shipmentMappingState.field_mapping ?? {};
    const next: Record<string, string> = {};
    for (const h of shipmentMappingState.file_headers) {
      const v = server[h];
      if (v && shipmentCanonSet.has(v)) next[h] = v;
    }
    setShipmentMapDraft(next);
  }, [
    isShipmentEvidence,
    shipmentMappingState?.id,
    shipmentMappingState?.file_headers,
    shipmentCanonSet,
    shipmentMappingState?.field_mapping,
  ]);

  const saveShipmentMapping = useMutation({
    mutationFn: async () => {
      const jid = shipmentMappingJobId;
      if (jid == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${jid}/shipment-field-mapping`), {
        method: 'PUT',
        headers: { ...defaultHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ field_mapping: shipmentMapDraft }),
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      const state = (await res.json()) as ShipmentMappingState;
      return { state, jid };
    },
    onSuccess: ({ jid }) => {
      void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', jid] });
      void qc.invalidateQueries({ queryKey: ['import-job', jid] });
    },
  });

  const shipmentValidateRun = useMutation({
    mutationFn: async () => {
      const jid = shipmentMappingJobId;
      if (jid == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${jid}/shipment-validate`), {
        method: 'POST',
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      await res.json();
      return { jid };
    },
    onSuccess: ({ jid }) => {
      void qc.invalidateQueries({ queryKey: ['import-job', jid] });
      void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', jid] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', jid] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void refetchPreview();
    },
  });

  const shipmentMappingDraftDirty = useMemo(() => {
    if (!shipmentMappingState?.file_headers?.length) return false;
    const server = shipmentMappingState.field_mapping ?? {};
    for (const h of shipmentMappingState.file_headers) {
      if ((shipmentMapDraft[h] ?? '') !== (server[h] ?? '')) return true;
    }
    return false;
  }, [shipmentMappingState, shipmentMapDraft]);

  type ShipmentApplyResponse = {
    id: number;
    status: string;
    stage: string | null;
    template_slug?: string | null;
    import_mode?: string | null;
    unresolved_distributor_candidates?: number;
    unresolved_customer_candidates?: number;
  };

  const shipmentApplyMut = useMutation({
    mutationFn: async () => {
      const id = shipmentEvidencePollJobId ?? lastJobId;
      if (id == null) throw new Error('No import job');
      return apiPost<ShipmentApplyResponse>(`/api/v1/shipment-evidence/jobs/${id}/apply`, {});
    },
    onMutate: () => {
      setShipmentApplyWarning(null);
    },
    onSuccess: (data) => {
      const id = data.id;
      void qc.invalidateQueries({ queryKey: ['import-job', id] });
      void qc.invalidateQueries({ queryKey: ['shipment-evidence-mapping-candidates', id] });
      const nd = data.unresolved_distributor_candidates;
      const nc = data.unresolved_customer_candidates;
      const parts: string[] = [];
      if (typeof nd === 'number' && nd > 0) {
        parts.push(`${nd} distributor mapping candidate(s) are still in needs_review.`);
      }
      if (typeof nc === 'number' && nc > 0) {
        parts.push(`${nc} channel partner mapping candidate(s) are still in needs_review.`);
      }
      if (parts.length > 0) {
        setShipmentApplyWarning(`${parts.join(' ')} You are not blocked — resolve them in the steward panel when ready.`);
      }
    },
  });

  const pmUpload = useMutation({
    mutationFn: async (file: File) => {
      if (sourceId === '') throw new Error('Select a data provider before uploading.');
      const fd = new FormData();
      fd.append('source_id', String(sourceId));
      fd.append('file', file);
      const res = await fetch(apiUrl('/api/v1/imports/product-master/jobs'), {
        method: 'POST',
        body: fd,
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<{ id: number; stage: string; file_headers: string[] }>;
    },
    onSuccess: (data) => {
      setLastJobId(data.id);
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['pm-import-state', data.id] });
    },
  });

  const savePmMapping = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/product-master/jobs/${lastJobId}/mapping`), {
        method: 'PUT',
        headers: { ...defaultHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ columns: pmDraftsToApiColumns(pmColumns) }),
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<{ id: number; stage: string }>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pm-import-state', lastJobId] });
    },
  });

  const validatePm = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const res = await fetch(apiUrl(`/api/v1/imports/product-master/jobs/${lastJobId}/validate`), {
        method: 'POST',
        headers: defaultHeaders,
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<{ validation_passed: boolean | null }>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pm-import-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
    },
  });

  const commitPm = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const fd = new FormData();
      const cd =
        !selectedTemplate?.destructive_apply_requires_confirm ||
        (selectedTemplate.destructive_apply_requires_confirm && confirmDestructive);
      fd.append('confirm_destructive', cd ? 'true' : 'false');
      const res = await fetch(apiUrl(`/api/v1/imports/product-master/jobs/${lastJobId}/commit`), {
        method: 'POST',
        body: fd,
        headers: defaultHeaders,
      });
      const text = await res.text();
      if (!res.ok) {
        throw new Error(await readFetchError(new Response(text, { status: res.status })));
      }
      return (text ? JSON.parse(text) : {}) as {
        pm_commit?: { outcome?: string; message?: string };
        status?: string;
        stage?: string;
      };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['pm-import-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
    },
  });

  const { data: pmJobState, refetch: refetchPmState } = useQuery({
    queryKey: ['pm-import-state', lastJobId],
    queryFn: ({ signal }) => apiGet<PmJobState>(`/api/v1/imports/product-master/jobs/${lastJobId}/state`, { signal }),
    enabled: Boolean(isPm && lastJobId != null),
    refetchInterval: (query) => {
      const externalBusy =
        savePmMapping.isPending || validatePm.isPending || commitPm.isPending;
      const data = query.state.data as PmJobState | undefined;
      const commitBusy =
        data?.status === 'commit_queued' || data?.status === 'commit_running';
      return externalBusy || commitBusy ? 2000 : false;
    },
  });

  const hdrKey = pmJobState?.file_headers?.join('|') ?? '';
  useEffect(() => {
    if (!isPm || activeStep !== 4 || !pmJobState?.file_headers?.length) return;
    setPmColumns(
      initPmColumnDrafts(pmJobState.file_headers, pmJobState.suggested_mapping, pmJobState.mapping_decisions)
    );
  }, [isPm, activeStep, lastJobId, hdrKey, pmJobState?.suggested_mapping, pmJobState?.mapping_decisions]);

  const downloadSample = useCallback(async () => {
    if (!selectedSlug) return;
    const res = await fetch(apiUrl(`/api/v1/imports/templates/${selectedSlug}/sample`), {
      headers: defaultHeaders,
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedSlug}_sample.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [selectedSlug]);

  const onFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const lower = file.name.toLowerCase();
      if (!lower.endsWith('.csv') && !lower.endsWith('.xlsx')) {
        if (isPm) {
          pmUpload.reset();
        } else {
          upload.reset();
        }
        return;
      }
      if (isPm) {
        pmUpload.mutate(file);
        return;
      }
      setLastGenericFile(file);
      setHistoricalValidatedJobId(null);
      const modeOverride =
        selectedSlug === 'historical_lineup' ||
        selectedSlug === 'distributor_inventory' ||
        selectedSlug === 'inbound_shipments'
          ? 'validate'
          : undefined;
      upload.mutate({ file, modeOverride });
    },
    [isPm, pmUpload, selectedSlug, upload]
  );

  const colDefs = useMemo<ColDef<Job>[]>(
    () => [
      {
        field: 'id',
        headerName: 'ID',
        width: 90,
        cellRenderer: (p: { value: number }) => (
          <Link
            component={NextLink}
            href={`/admin/imports?job=${p.value}`}
            underline="hover"
            color="primary"
          >
            {p.value}
          </Link>
        ),
      },
      { field: 'template_slug', headerName: 'Template', minWidth: 140 },
      { field: 'import_mode', headerName: 'Mode', width: 100 },
      { field: 'file_name', headerName: 'File', flex: 1, minWidth: 160 },
      { field: 'status', headerName: 'Status' },
      { field: 'stage', headerName: 'Stage' },
      {
        field: 'archived_at',
        headerName: 'Archived',
        width: 170,
        hide: !showArchivedImportJobs,
        valueFormatter: (p) => (p.value != null ? String(p.value) : '—'),
      },
      { field: 'error_summary', headerName: 'Notes', flex: 1, minWidth: 200 },
    ],
    [showArchivedImportJobs],
  );

  const jobsList = jobs ?? [];

  useEffect(() => {
    if (jobsBulkSelectionMode !== 'selecting') {
      jobsGridApiRef.current?.deselectAll();
      setJobsSelectedCount(0);
    }
  }, [jobsBulkSelectionMode]);

  useEffect(() => {
    setJobsVisibleRowCount(jobsList.length);
  }, [jobsList.length]);

  const jobsGridOptions = useMemo<GridOptions<Job>>(() => {
    const base: GridOptions<Job> = {
      onGridReady: (e) => {
        jobsGridApiRef.current = e.api;
        setJobsVisibleRowCount(e.api.getDisplayedRowCount());
      },
      onFilterChanged: (e) => {
        if (jobsBulkSelectionMode === 'selecting') setJobsVisibleRowCount(e.api.getDisplayedRowCount());
      },
      onSortChanged: (e) => {
        if (jobsBulkSelectionMode === 'selecting') setJobsVisibleRowCount(e.api.getDisplayedRowCount());
      },
    };
    if (jobsBulkSelectionMode !== 'selecting') return base;
    return {
      ...base,
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        setJobsSelectedCount(e.api.getSelectedRows().length);
      },
    };
  }, [jobsBulkSelectionMode]);

  const openImportJobBulkDeletePreview = useCallback(async () => {
    const api = jobsGridApiRef.current;
    if (!api) return;
    const ids = api.getSelectedRows().map((r) => r.id);
    if (!ids.length) return;
    setImportJobBulkDeleteBusy(true);
    setImportJobDeleteSemanticArtifacts(false);
    setImportJobBulkDeleteAck(false);
    try {
      const data = await apiPost<ImportJobBulkDeletePreview>('/api/v1/imports/jobs/bulk-delete-preview', { job_ids: ids });
      setImportJobBulkDeletePreview(data);
      setImportJobBulkDeleteOpen(true);
    } catch (e) {
      alert(safeDisplayError(e));
    } finally {
      setImportJobBulkDeleteBusy(false);
    }
  }, []);

  const closeImportJobBulkDeleteDialog = useCallback(() => {
    if (importJobBulkDeleteBusy) return;
    setImportJobBulkDeleteOpen(false);
    setImportJobBulkDeletePreview(null);
  }, [importJobBulkDeleteBusy]);

  const confirmImportJobBulkDelete = useCallback(async () => {
    if (!importJobBulkDeletePreview) return;
    setImportJobBulkDeleteBusy(true);
    try {
      await apiPost('/api/v1/imports/jobs/bulk-delete-confirm', {
        job_ids: importJobBulkDeletePreview.job_ids,
        delete_semantic_artifacts: importJobDeleteSemanticArtifacts,
      });
      setImportJobBulkDeleteOpen(false);
      setImportJobBulkDeletePreview(null);
      setJobsBulkSelectionMode('normal');
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    } catch (e) {
      alert(safeDisplayError(e));
    } finally {
      setImportJobBulkDeleteBusy(false);
    }
  }, [importJobBulkDeletePreview, importJobDeleteSemanticArtifacts, qc]);

  const canGoUploadGeneric =
    selectedSlug &&
    (!selectedTemplate?.requires_provider || sourceId !== '') &&
    (!selectedTemplate?.destructive_apply_requires_confirm || importMode === 'validate' || confirmDestructive);

  const canPmUpload =
    Boolean(selectedSlug) &&
    Boolean(selectedTemplate?.requires_provider ? sourceId !== '' : true) &&
    sourceId !== '';

  const canGoUpload = isPm ? canPmUpload : canGoUploadGeneric;

  const identityTargetSet = useMemo(
    () => new Set(pmJobState?.identity_targets ?? ['technical_product_id']),
    [pmJobState?.identity_targets]
  );

  const coreTargetKeys = useMemo(
    () =>
      new Set([
        'technical_product_id',
        'display_name',
        'market_sku',
        'model_family',
        'source_product_code',
        'barcode_ean',
        'barcode_upc',
        'category',
        'product_line',
        'series',
        'business_unit',
        'form_factor',
        'channel_code',
        'price_band',
        'country_code',
        'lifecycle_status',
        'launch_date',
        'end_of_life_date',
      ]),
    []
  );

  const visiblePmColumns = useMemo(() => {
    return pmColumns.filter((row) => {
      const t = row.target.trim();
      if (pmRowFilter === 'unmapped') return !t;
      if (pmRowFilter === 'mapped') return Boolean(t);
      if (pmRowFilter === 'core') return !t || coreTargetKeys.has(t);
      return true;
    });
  }, [pmColumns, pmRowFilter, coreTargetKeys]);

  const pmTargetOptions = useMemo((): PmFieldDefinition[] => {
    const raw = pmJobState?.field_definitions;
    if (raw && raw.length > 0) {
      return sortPmFieldDefinitions(raw);
    }
    const keys = pmJobState?.canonical_fields ?? [];
    return sortPmFieldDefinitions(
      keys.map((k) => ({
        key: k,
        group: 'optional',
        label: k,
        importance: 'medium',
        dim_persistence: 'canonical',
        description: '',
      }))
    );
  }, [pmJobState?.field_definitions, pmJobState?.canonical_fields]);

  /** Per-row mapping picker options (ordering + duplicate awareness). */
  const pmEnrichedTargetsByHeader = useMemo(() => {
    const req = pmJobState?.required_fields ?? ['display_name'];
    const idt = pmJobState?.identity_targets ?? ['technical_product_id'];
    const usage = buildTargetUsageMap(pmColumns);
    const sentinel: EnrichedPmTargetOption = {
      key: '',
      label: '(Unmapped)',
      group: 'optional',
      importance: 'low',
      dim_persistence: '',
      description:
        'Not mapped to a system field; choose a disposition below for extra columns.',
      sortTier: 62,
      sectionKey: 'unmapped',
      sectionLabel: 'Leave unmapped',
      badgeTexts: [],
      duplicateFromHeaders: [],
    };
    const out: Record<string, EnrichedPmTargetOption[]> = {};
    for (const col of pmColumns) {
      const enriched = enrichPmMappingTargets({
        defs: pmTargetOptions,
        requiredFields: req,
        identityTargets: idt,
        usage,
        currentHeader: col.header,
      });
      out[col.header] = [sentinel, ...enriched];
    }
    return out;
  }, [
    pmColumns,
    pmTargetOptions,
    pmJobState?.required_fields,
    pmJobState?.identity_targets,
  ]);

  const inferredByHeader = useMemo(() => {
    const cols = pmJobState?.inferred_schema?.columns;
    if (!cols?.length) return {} as Record<string, InferredColumn>;
    return Object.fromEntries(cols.map((c) => [c.name, c]));
  }, [pmJobState?.inferred_schema?.columns]);

  const mappedTargets = useMemo(
    () =>
      pmColumns
        .map((c) => c.target.trim())
        .filter((t) => t.length > 0),
    [pmColumns]
  );

  const requiredOk = useMemo(() => {
    const req = pmJobState?.required_fields ?? ['display_name'];
    const coreOk = req.every((f) => mappedTargets.filter((t) => t === f).length === 1);
    const idHits = mappedTargets.filter((t) => identityTargetSet.has(t));
    const identityOk = idHits.length === 1;
    return coreOk && identityOk;
  }, [pmJobState?.required_fields, mappedTargets, identityTargetSet]);

  const pmMappingSummary = useMemo(() => {
    const idHits = mappedTargets.filter((t) => identityTargetSet.has(t));
    const commercial = new Set(['market_sku', 'model_family', 'source_product_code']);
    const classification = new Set([
      'category',
      'form_factor',
      'price_band',
      'series',
      'product_line',
      'business_unit',
      'country_code',
    ]);
    return {
      requiredCoreOk: (pmJobState?.required_fields ?? ['display_name']).every(
        (f) => mappedTargets.filter((t) => t === f).length === 1
      ),
      identityOk: idHits.length === 1,
      identityTarget: idHits[0] ?? null,
      commercialMapped: mappedTargets.filter((t) => commercial.has(t)).length,
      classificationMapped: mappedTargets.filter((t) => classification.has(t)).length,
      unmappedColumns: pmColumns.filter((c) => !c.target.trim()).length,
      stagedDisposition: pmColumns.filter((c) => !c.target.trim() && c.disposition === 'stage_raw').length,
    };
  }, [mappedTargets, pmColumns, pmJobState?.required_fields, identityTargetSet]);

  const selectedBulkCount = useMemo(
    () => Object.values(pmBulkSelected).filter(Boolean).length,
    [pmBulkSelected]
  );

  const applySuggestedMappingsOnly = useCallback(() => {
    if (!pmJobState?.file_headers?.length) return;
    setPmColumns(
      initPmColumnDrafts(pmJobState.file_headers, pmJobState.suggested_mapping, null)
    );
    setPmBulkSelected({});
  }, [pmJobState?.file_headers, pmJobState?.suggested_mapping]);

  const clearAllMappings = useCallback(() => {
    setPmColumns((prev) =>
      prev.map((c) => ({ ...c, target: '', disposition: 'ignore' as PmDisposition }))
    );
    setPmBulkSelected({});
  }, []);

  const bulkUnmappedSetIgnore = useCallback(() => {
    setPmColumns((prev) =>
      prev.map((c) => (!c.target.trim() ? { ...c, disposition: 'ignore' as PmDisposition } : c))
    );
  }, []);

  const bulkUnmappedSetStage = useCallback(() => {
    setPmColumns((prev) =>
      prev.map((c) => (!c.target.trim() ? { ...c, disposition: 'stage_raw' as PmDisposition } : c))
    );
  }, []);

  const bulkDispositionForSelection = useCallback(
    (d: PmDisposition) => {
      setPmColumns((prev) =>
        prev.map((c) => (pmBulkSelected[c.header] ? { ...c, disposition: d } : c))
      );
    },
    [pmBulkSelected]
  );

  const visibleHeaderList = useMemo(() => visiblePmColumns.map((r) => r.header), [visiblePmColumns]);
  const allVisibleSelected =
    visibleHeaderList.length > 0 && visibleHeaderList.every((h) => pmBulkSelected[h]);

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Imports' }]} title="Data & imports" />
      <Alert severity="info" sx={{ mb: 2 }}>
        <strong>Guided import:</strong> pick an <strong>import type</strong> first (what the file means), then a{' '}
        <strong>data provider</strong> (which feed or instance). Product Master uses a{' '}
        <strong>governed mapping</strong>: only approved catalog fields, explicit handling for extra columns, then{' '}
        <strong>validate</strong> before <strong>commit</strong>.
      </Alert>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          New import
        </Typography>
        <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 3 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {isPm && lastJobId != null ? (
          <PmImportProgressPanel
            progress={pmJobState?.progress ?? undefined}
            jobStatus={pmJobState?.status ?? null}
            isValidating={validatePm.isPending}
            isCommitting={commitPm.isPending}
            isSavingMapping={savePmMapping.isPending}
          />
        ) : null}

        {isJobRevisitMode && isPm ? (
          <Alert severity="info" sx={{ mb: 2 }}>
            Viewing previous Product Master job <strong>#{lastJobId}</strong> in read-only mode. Full PM revisit is not yet
            supported in this view. Row diagnostics are visible in the <strong>Import jobs</strong> grid below.
          </Alert>
        ) : null}

        {activeStep === 0 ? (
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Choose the import <strong>type</strong> that matches your file (not the low-level parser id).
            </Typography>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              {visibleTemplates.map((t) => (
                <Card key={t.slug} variant="outlined" sx={{ width: 280 }}>
                  <CardActionArea
                    onClick={() => {
                      setSelectedSlug(t.slug);
                      setSourceId('');
                      setImportMode(
                        t.slug === 'product_master' ||
                          t.slug === 'historical_lineup' ||
                          t.slug === 'distributor_inventory' ||
                          t.slug === 'inbound_shipments'
                          ? 'validate'
                          : 'apply'
                      );
                      setConfirmDestructive(false);
                      setLastGenericFile(null);
                      setHistoricalValidatedJobId(null);
                      setIsJobRevisitMode(false);
                      setHlMappingEdits({});
                      setShowMappingReview(false);
                      setActiveStep(1);
                    }}
                  >
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600}>
                        {t.display_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                        {t.slug}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {t.description ?? '—'}
                      </Typography>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                        {!t.pipeline_ready ? <Chip size="small" label="Pipeline scaffold" color="warning" /> : null}
                        {t.destructive_apply_requires_confirm ? (
                          <Chip size="small" label="Apply needs confirm" variant="outlined" />
                        ) : null}
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 1 ? (
          <Stack spacing={2}>
            <Typography variant="body2">
              Selected type: <strong>{selectedTemplate?.display_name}</strong> ({selectedSlug})
            </Typography>
            {selectedTemplate?.requires_provider ? (
              <FormControl size="small" sx={{ maxWidth: 420 }}>
                <InputLabel id="prov-label">Data provider / feed</InputLabel>
                <Select
                  labelId="prov-label"
                  label="Data provider / feed"
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value === '' ? '' : Number(e.target.value))}
                >
                  {(sources ?? []).map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.name} ({s.code})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : (
              <Alert severity="info">This import type does not require a separate provider instance.</Alert>
            )}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(0)}>Back</Button>
              <Button
                variant="contained"
                disabled={Boolean(selectedTemplate?.requires_provider && sourceId === '')}
                onClick={() => setActiveStep(2)}
              >
                Next
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 2 && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Expected columns</Typography>
            <Typography variant="body2">
              <strong>Required:</strong> {selectedTemplate.required_fields.join(', ') || '—'}
            </Typography>
            <Typography variant="body2">
              <strong>Optional:</strong> {selectedTemplate.optional_fields.join(', ') || '—'}
            </Typography>
            <Typography variant="body2">
              <strong>Accepted files:</strong> {selectedTemplate.accepted_file_types.join(', ')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              <strong>What happens:</strong>{' '}
              {describeTemplateBehavior(selectedTemplate, isPm, isDsi)}
            </Typography>
            {selectedTemplate.slug === 'historical_lineup' ? (
              <Alert severity="info">
                Preferred workbook shape: keep the lineup data on a named sheet (for example <strong>NB</strong>) with a
                single header row near the top. Title/blank rows before the header are tolerated. Validation reports
                detected sheet and header row using <code>historical_lineup_sheet_summary</code>.
              </Alert>
            ) : null}
            {selectedTemplate.slug === 'distributor_inventory' ? (
              <Stack spacing={1}>
                <Alert severity="info" data-testid="dsi-contract-copy">
                  The system accepts different distributor column layouts, but values must map into the required business
                  fields before apply. Map your file columns to canonical targets (for example distributor account, product
                  identifier, dates, quantities).
                </Alert>
                <Alert severity="info" data-testid="dsi-unit-price-copy">
                  <strong>Unit sell-out price</strong> fields are <strong>ex tax / ex VAT</strong> per unit where supplied.
                  They are not the same as total line revenue — map revenue separately when both exist.
                </Alert>
                <Alert severity="warning" data-testid="dsi-shipping-copy">
                  OTW/POD/shipping-like columns should be mapped to ignored shipping evidence only. They are preserved as raw
                  payload but are not written to inbound shipments — use the Inbound shipments import for shipping history.
                </Alert>
                <Alert severity="info" data-testid="dsi-customer-copy">
                  Distributor customer names may differ by source. Unresolved names are staged and surfaced as aggregated
                  mapping candidates; they are <strong>not</strong> auto-created as customers. Recurring names can be mapped
                  to existing customers or promoted through controlled mapping review.
                </Alert>
                <Typography variant="caption" color="text.secondary" component="div">
                  <strong>Sell-out contract (per row):</strong> distributor + product + transaction date + quantity sold + a
                  resolvable customer (or Open Channel evidence); optional unit price ex tax, reported revenue, currency,
                  channel/region. <strong>Inventory snapshot:</strong> distributor + product + snapshot date + stock on hand.
                  Rows may contribute to one or both contracts when both sets of fields validate.
                </Typography>
              </Stack>
            ) : null}
            {isPm ? (
              <Button startIcon={<DownloadOutlinedIcon />} variant="outlined" size="small" onClick={() => void downloadSample()}>
                Download sample CSV
              </Button>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(1)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(3)}>
                Next
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 3 && selectedTemplate && !isPm && !isShipmentEvidence ? (
          <Stack spacing={2}>
            <FormControl size="small" sx={{ maxWidth: 360 }}>
              <InputLabel id="mode-label">Import mode</InputLabel>
              <Select
                labelId="mode-label"
                label="Import mode"
                value={importMode}
                disabled={
                  selectedTemplate.slug === 'historical_lineup' ||
                  selectedTemplate.slug === 'distributor_inventory' ||
                  selectedTemplate.slug === 'inbound_shipments'
                }
                onChange={(e) => setImportMode(e.target.value as 'validate' | 'apply')}
              >
                <MenuItem value="validate">Validate only (no catalog writes)</MenuItem>
                <MenuItem value="apply">Apply / upsert (when supported)</MenuItem>
              </Select>
            </FormControl>
            {selectedTemplate.slug === 'historical_lineup' ? (
              <Alert severity="info">
                Historical lineup imports run <strong>validate preview first</strong>. After preview loads, use{' '}
                <strong>Apply validated file</strong> in the upload step.
              </Alert>
            ) : null}
            {selectedTemplate.slug === 'distributor_inventory' ? (
              <Alert severity="info">
                This import always starts in <strong>validate</strong> mode. Apply runs only on the last step after
                column mapping and preview.
              </Alert>
            ) : null}
            {selectedTemplate.destructive_apply_requires_confirm && importMode === 'apply' ? (
              <FormControlLabel
                control={<Checkbox checked={confirmDestructive} onChange={(_, c) => setConfirmDestructive(c)} />}
                label="I understand this can overwrite existing product fields for matching SKUs."
              />
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(2)}>Back</Button>
              <Button
                variant="contained"
                disabled={
                  selectedTemplate.destructive_apply_requires_confirm && importMode === 'apply' && !confirmDestructive
                }
                onClick={() => setActiveStep(4)}
              >
                Next
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 3 && selectedTemplate && isPm ? (
          <Stack spacing={2}>
            <Typography variant="body2">
              Upload for <strong>{selectedTemplate.display_name}</strong> using provider{' '}
              <strong>{(sources ?? []).find((s) => s.id === sourceId)?.name ?? '—'}</strong>. Headers are inferred
              immediately; mapping and validate/commit follow in the next steps.
            </Typography>
            {!canGoUpload ? <Alert severity="warning">Select a data provider before uploading.</Alert> : null}
            <Box
              onDragEnter={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                const f = e.dataTransfer.files?.[0];
                onFile(f);
              }}
              sx={{
                border: '2px dashed',
                borderColor: dragActive ? 'primary.main' : 'divider',
                borderRadius: 2,
                px: 3,
                py: 4,
                textAlign: 'center',
                bgcolor: dragActive ? 'action.selected' : 'action.hover',
              }}
            >
              <CloudUploadOutlinedIcon sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <Typography variant="subtitle1" fontWeight={600}>
                Drop CSV or XLSX here
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Or choose a file. No catalog writes until you pass validation and commit on the last step.
              </Typography>
              <Button variant="contained" component="label" disabled={!canGoUpload || pmUpload.isPending}>
                Choose file
                <input
                  hidden
                  type="file"
                  accept=".csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(e) => {
                    onFile(e.target.files?.[0]);
                    e.target.value = '';
                  }}
                />
              </Button>
            </Box>
            {pmUpload.isPending ? <LinearProgress /> : null}
            {pmUpload.isError ? (
              <Alert severity="error">{safeDisplayError(pmUpload.error)}</Alert>
            ) : null}
            {pmUpload.isSuccess && lastJobId != null ? (
              <Alert severity="success">
                Job <strong>#{lastJobId}</strong> staged. File headers:{' '}
                {Array.isArray(pmUpload.data?.file_headers) ? pmUpload.data.file_headers.join(', ') || '—' : '—'}
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(2)}>Back</Button>
              <Button variant="contained" disabled={lastJobId == null} onClick={() => setActiveStep(4)}>
                Next: column mapping
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 4 && isPm && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Map file columns → canonical fields</Typography>
            <Alert severity={requiredOk ? 'success' : 'warning'}>
              <strong>Required core:</strong> map <strong>display_name</strong> once, and exactly one{' '}
              <strong>technical_product_id</strong> (manufacturer / exact technical id). Use tooltips in the target picker
              for semantics.
              <br />
              <strong>Optional:</strong> market_sku, model_family, barcodes, classification, lifecycle, and
              source_product_code (feed-specific id) as needed.
            </Alert>
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }}>
              <Typography variant="caption" fontWeight={600} display="block" gutterBottom>
                Mapping summary
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1} useFlexGap>
                <Chip
                  size="small"
                  color={pmMappingSummary.requiredCoreOk ? 'success' : 'warning'}
                  label={`Required core: ${pmMappingSummary.requiredCoreOk ? 'OK' : 'incomplete'}`}
                />
                <Chip
                  size="small"
                  color={pmMappingSummary.identityOk ? 'success' : 'warning'}
                  label={`Identity (${pmMappingSummary.identityTarget ?? 'missing'}): ${
                    pmMappingSummary.identityOk ? 'OK' : 'need technical_product_id'
                  }`}
                />
                <Chip size="small" variant="outlined" label={`Commercial fields: ${pmMappingSummary.commercialMapped}`} />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Classification fields: ${pmMappingSummary.classificationMapped}`}
                />
                <Chip size="small" variant="outlined" label={`Unmapped columns: ${pmMappingSummary.unmappedColumns}`} />
                <Chip size="small" variant="outlined" label={`Staged metadata cols: ${pmMappingSummary.stagedDisposition}`} />
              </Stack>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={1.5}>
                <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center" useFlexGap>
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="pm-filter-label">Row filter</InputLabel>
                    <Select
                      labelId="pm-filter-label"
                      label="Row filter"
                      value={pmRowFilter}
                      onChange={(e) =>
                        setPmRowFilter(e.target.value as 'all' | 'unmapped' | 'mapped' | 'core')
                      }
                    >
                      <MenuItem value="all">All columns ({pmColumns.length})</MenuItem>
                      <MenuItem value="unmapped">Unmapped only</MenuItem>
                      <MenuItem value="mapped">Mapped only</MenuItem>
                      <MenuItem value="core">Core / important targets</MenuItem>
                    </Select>
                  </FormControl>
                  <Typography variant="caption" color="text.secondary">
                    Showing {visiblePmColumns.length} of {pmColumns.length}
                  </Typography>
                </Stack>
                <Stack direction="row" flexWrap="wrap" gap={1} useFlexGap alignItems="center">
                  <Button size="small" variant="outlined" onClick={bulkUnmappedSetIgnore}>
                    All unmapped → Ignore
                  </Button>
                  <Button size="small" variant="outlined" onClick={bulkUnmappedSetStage}>
                    All unmapped → Stage metadata
                  </Button>
                  <Button size="small" variant="outlined" onClick={applySuggestedMappingsOnly}>
                    Apply suggested mappings only
                  </Button>
                  <Button size="small" variant="outlined" color="warning" onClick={clearAllMappings}>
                    Clear all mappings
                  </Button>
                </Stack>
                <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center" useFlexGap>
                  <Typography variant="caption">
                    Selected rows: {selectedBulkCount}
                  </Typography>
                  <Button
                    size="small"
                    disabled={!selectedBulkCount}
                    onClick={() => bulkDispositionForSelection('ignore')}
                  >
                    Set disposition Ignore
                  </Button>
                  <Button
                    size="small"
                    disabled={!selectedBulkCount}
                    onClick={() => bulkDispositionForSelection('stage_raw')}
                  >
                    Set disposition Stage
                  </Button>
                  <Button
                    size="small"
                    disabled={!selectedBulkCount}
                    onClick={() => bulkDispositionForSelection('attribute_candidate')}
                  >
                    Set disposition Steward review
                  </Button>
                </Stack>
              </Stack>
            </Paper>
            <Typography variant="caption" color="text.secondary">
              Unmapped columns need a disposition: ignore, retain as staged metadata, or flag for steward review (no new schema
              columns are created here).
            </Typography>
            {pmJobState?.inferred_schema?.row_count != null ? (
              <Typography variant="caption" color="text.secondary" display="block">
                Loaded <strong>{pmJobState.inferred_schema.row_count}</strong> data row(s); sample values are taken from the first
                non-empty cells per column (up to three).
              </Typography>
            ) : null}
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={allVisibleSelected}
                      indeterminate={
                        visibleHeaderList.some((h) => pmBulkSelected[h]) && !allVisibleSelected
                      }
                      onChange={() => {
                        setPmBulkSelected((prev) => {
                          const next = { ...prev };
                          const on = !allVisibleSelected;
                          visibleHeaderList.forEach((h) => {
                            if (on) next[h] = true;
                            else delete next[h];
                          });
                          return next;
                        });
                      }}
                    />
                  </TableCell>
                  <TableCell>File header</TableCell>
                  <TableCell sx={{ minWidth: 220 }}>Sample values</TableCell>
                  <TableCell>Maps to</TableCell>
                  <TableCell>Unmapped handling</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visiblePmColumns.map((row) => (
                  <TableRow key={row.header}>
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        checked={Boolean(pmBulkSelected[row.header])}
                        onChange={() =>
                          setPmBulkSelected((prev) => ({
                            ...prev,
                            [row.header]: !prev[row.header],
                          }))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Typography fontWeight={600}>{row.header}</Typography>
                      {inferredByHeader[row.header]?.dtype ? (
                        <Typography variant="caption" color="text.secondary" display="block">
                          {inferredByHeader[row.header].dtype}
                        </Typography>
                      ) : null}
                      {(() => {
                        const sug = pmJobState?.suggested_mapping?.[row.header];
                        if (!sug) return null;
                        const act = sug.mapper_action;
                        if (!sug?.reasons?.length && sug?.confidence == null && !sug?.runner_up && !act) return null;
                        const parts: string[] = [];
                        if (sug.from_source_memory) parts.push('Source memory');
                        if (act === 'auto_map' && sug.target) {
                          parts.push(`Auto-map: ${sug.target}`);
                          if (sug.confidence != null) parts.push(`${Math.round(sug.confidence * 100)}%`);
                        } else if (act === 'suggest' && (sug.suggested_target || sug.target)) {
                          parts.push(`Suggested: ${sug.suggested_target ?? sug.target}`);
                          if (sug.confidence != null) parts.push(`${Math.round(sug.confidence * 100)}%`);
                        } else if (act === 'recommend_stage_metadata') {
                          parts.push('Recommended: Stage as metadata');
                        } else if (act === 'recommend_ignore') {
                          parts.push('Recommended: Ignore');
                        } else if (act === 'no_strong_suggestion') {
                          parts.push('No strong suggestion');
                          if (sug.hint_target) parts.push(`Optional hint: ${sug.hint_target}`);
                          else if (sug.runner_up?.target) parts.push(`Alternative: ${sug.runner_up.target}`);
                        } else if (sug.target) {
                          parts.push(`Map: ${sug.target}`);
                          if (sug.confidence != null) parts.push(`${Math.round(sug.confidence * 100)}%`);
                        }
                        const detail =
                          (sug.reasons?.length ? sug.reasons.map(formatPmSuggestReason).join(' · ') : '') +
                          (sug.runner_up?.target && sug.target && act !== 'no_strong_suggestion'
                            ? ` · Alternative: ${sug.runner_up.target}`
                            : '');
                        const tip = [parts.join(' — '), detail].filter(Boolean).join('\n');
                        const chipLabel =
                          act === 'auto_map' && sug.target
                            ? `Auto-map · ${sug.target}`
                            : act === 'suggest' && (sug.suggested_target || sug.target)
                              ? `Suggested · ${sug.suggested_target ?? sug.target}`
                              : act === 'recommend_stage_metadata'
                                ? 'Stage metadata'
                                : act === 'recommend_ignore'
                                  ? 'Ignore'
                                  : act === 'no_strong_suggestion'
                                    ? 'No strong mapping'
                                    : parts[0] ?? '';
                        const chipColor =
                          act === 'auto_map'
                            ? 'success'
                            : act === 'suggest'
                              ? 'info'
                              : act === 'recommend_stage_metadata'
                                ? 'warning'
                                : act === 'recommend_ignore'
                                  ? 'default'
                                  : 'default';
                        return (
                          <Tooltip title={tip || 'Mapper guidance'}>
                            <Stack spacing={0.5} sx={{ mt: 0.25 }}>
                              {chipLabel ? (
                                <Chip size="small" variant="outlined" color={chipColor} label={chipLabel} sx={{ width: 'fit-content' }} />
                              ) : null}
                              <Typography variant="caption" color="text.secondary" display="block">
                                {parts.join(' · ') || '—'}
                              </Typography>
                            </Stack>
                          </Tooltip>
                        );
                      })()}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 280, wordBreak: 'break-word' }}>
                      <Typography variant="body2" color="text.secondary">
                        {formatPmSamples(inferredByHeader[row.header]?.sample)}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ minWidth: 280 }}>
                      <Autocomplete
                        size="small"
                        options={pmEnrichedTargetsByHeader[row.header] ?? []}
                        filterOptions={(opts, state) =>
                          filterAndSortPmTargets(opts as EnrichedPmTargetOption[], state)
                        }
                        groupBy={(opt) =>
                          'sectionLabel' in opt && opt.sectionLabel
                            ? opt.sectionLabel
                            : PM_GROUP_LABEL[opt.group] ?? opt.group
                        }
                        getOptionLabel={(opt) => (opt.key ? `${opt.label} (${opt.key})` : opt.label)}
                        isOptionEqualToValue={(a, b) => a.key === b.key}
                        value={(() => {
                          const t = row.target.trim();
                          const base = pmEnrichedTargetsByHeader[row.header] ?? [];
                          const f = base.find((o) => o.key === t);
                          if (f) return f;
                          if (t) {
                            return {
                              key: t,
                              label: t,
                              group: 'optional',
                              importance: 'low',
                              dim_persistence: '',
                              description: '',
                              sortTier: 99,
                              sectionKey: 'legacy',
                              sectionLabel: 'Saved / unknown key',
                              badgeTexts: [],
                              duplicateFromHeaders: [],
                            } as EnrichedPmTargetOption;
                          }
                          return (
                            base[0] ?? {
                              key: '',
                              label: '(Unmapped)',
                              group: 'optional',
                              importance: 'low',
                              dim_persistence: '',
                              description: '',
                              sortTier: 62,
                              sectionKey: 'unmapped',
                              sectionLabel: 'Leave unmapped',
                              badgeTexts: [],
                              duplicateFromHeaders: [],
                            }
                          );
                        })()}
                        onChange={(_, opt) => {
                          const v = opt?.key ?? '';
                          setPmColumns((prev) =>
                            prev.map((p) =>
                              p.header === row.header
                                ? { ...p, target: v, disposition: v ? 'ignore' : p.disposition }
                                : p
                            )
                          );
                        }}
                        renderOption={(props, opt) => (
                          <li {...props} key={opt.key || 'blank'}>
                            <Stack direction="row" alignItems="flex-start" spacing={0.5} sx={{ width: '100%', py: 0.25 }}>
                              <Box sx={{ flex: 1, minWidth: 0 }}>
                                <Stack direction="row" alignItems="center" spacing={0.5} flexWrap="wrap" useFlexGap>
                                  <Typography variant="body2">{opt.label}</Typography>
                                  {(opt as EnrichedPmTargetOption).badgeTexts?.map((b) => (
                                    <Chip key={b} size="small" variant="outlined" label={b} sx={{ height: 20 }} />
                                  ))}
                                </Stack>
                                <Typography variant="caption" color="text.secondary">
                                  {opt.key
                                    ? `${opt.key} · ${opt.role ?? opt.dim_persistence}`
                                    : opt.description}
                                </Typography>
                                {(opt as EnrichedPmTargetOption).duplicateFromHeaders?.length ? (
                                  <Typography variant="caption" color="warning.main" display="block">
                                    Also mapped from:{' '}
                                    {(opt as EnrichedPmTargetOption).duplicateFromHeaders!.join(', ')}
                                  </Typography>
                                ) : null}
                              </Box>
                              {opt.description ? (
                                <Tooltip title={opt.description}>
                                  <InfoOutlinedIcon sx={{ fontSize: 18, color: 'text.secondary', mt: 0.25 }} />
                                </Tooltip>
                              ) : null}
                            </Stack>
                          </li>
                        )}
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="Maps to"
                            placeholder="Search targets…"
                            InputProps={{
                              ...params.InputProps,
                              endAdornment: (
                                <>
                                  {(() => {
                                    const sel = pmTargetOptions.find((o) => o.key === row.target.trim());
                                    const dup =
                                      pmEnrichedTargetsByHeader[row.header]?.find(
                                        (o) => o.key === row.target.trim()
                                      )?.duplicateFromHeaders ?? [];
                                    return sel?.description || dup.length ? (
                                      <InputAdornment position="end">
                                        <Tooltip
                                          title={
                                            [
                                              dup.length
                                                ? `Duplicate: also used by ${dup.join(', ')}`
                                                : '',
                                              sel?.description ?? '',
                                            ]
                                              .filter(Boolean)
                                              .join(' — ') || ''
                                          }
                                        >
                                          <InfoOutlinedIcon
                                            sx={{
                                              fontSize: 18,
                                              cursor: 'help',
                                              color: dup.length ? 'warning.main' : 'text.secondary',
                                            }}
                                          />
                                        </Tooltip>
                                      </InputAdornment>
                                    ) : null;
                                  })()}
                                  {params.InputProps.endAdornment}
                                </>
                              ),
                            }}
                          />
                        )}
                      />
                    </TableCell>
                    <TableCell sx={{ minWidth: 220 }}>
                      <FormControl size="small" fullWidth disabled={Boolean(row.target.trim())}>
                        <InputLabel id={`disp-${row.header}`}>Disposition</InputLabel>
                        <Select
                          labelId={`disp-${row.header}`}
                          label="Disposition"
                          value={row.target.trim() ? 'ignore' : row.disposition}
                          onChange={(e) => {
                            const v = e.target.value as PmDisposition;
                            setPmColumns((prev) =>
                              prev.map((p) => (p.header === row.header ? { ...p, disposition: v } : p))
                            );
                          }}
                        >
                          <MenuItem value="ignore">Ignore</MenuItem>
                          <MenuItem value="stage_raw">Retain as staged metadata</MenuItem>
                          <MenuItem value="attribute_candidate">Request new field (steward review)</MenuItem>
                        </Select>
                      </FormControl>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {savePmMapping.isError ? (
              <Alert severity="error">{safeDisplayError(savePmMapping.error)}</Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button onClick={() => setActiveStep(3)}>Back</Button>
              <Button
                variant="outlined"
                disabled={!requiredOk || savePmMapping.isPending}
                onClick={() => void savePmMapping.mutateAsync().then(() => void refetchPmState())}
              >
                Save mapping
              </Button>
              <Button
                variant="contained"
                disabled={!requiredOk || savePmMapping.isPending}
                onClick={() =>
                  void savePmMapping.mutateAsync().then(() => {
                    void refetchPmState();
                    setActiveStep(5);
                  })
                }
              >
                Save & continue to validate
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 5 && isPm ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Validate import (no catalog writes)</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button variant="contained" onClick={() => void validatePm.mutateAsync()} disabled={validatePm.isPending}>
                Run validation
              </Button>
              {pmJobState?.validation_passed === true ? <Chip color="success" label="Passed" /> : null}
              {pmJobState?.validation_passed === false ? <Chip color="error" label="Failed" /> : null}
              {pmJobState?.validation_passed == null ? <Chip variant="outlined" label="Not run yet" /> : null}
            </Stack>
            {pmJobState?.error_summary ? <Alert severity="warning">{pmJobState.error_summary}</Alert> : null}
            {validatePm.isError ? (
              <Alert severity="error">{safeDisplayError(validatePm.error)}</Alert>
            ) : null}
            {previewRows && previewRows.length > 0 ? (
              <>
                {selectedTemplate?.slug === 'historical_lineup' ? (
                  <Alert severity="info">
                    Legacy workbook tolerance is enabled. Review rows with <code>historical_lineup_sheet_summary</code>,{' '}
                    <code>low_mapping_confidence</code>, and unresolved entity diagnostics before apply.
                  </Alert>
                ) : null}
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Row</TableCell>
                      <TableCell>Severity</TableCell>
                      <TableCell>Code</TableCell>
                      <TableCell>Message</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {previewRows.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>{r.row_number}</TableCell>
                        <TableCell>{r.severity}</TableCell>
                        <TableCell>{r.code}</TableCell>
                        <TableCell>{r.message}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            ) : null}
            {pmJobState?.staged_metadata_preview && Object.keys(pmJobState.staged_metadata_preview).length > 0 ? (
              <Alert severity="info">
                Staged metadata rows (preview): <strong>{Object.keys(pmJobState.staged_metadata_preview).length}</strong> index
                keys — values are merged into <code>specs_json.import_staging</code> on commit.
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(4)}>Back</Button>
              <Button variant="contained" disabled={pmJobState?.validation_passed !== true} onClick={() => setActiveStep(6)}>
                Continue to commit
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 6 && isPm && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Commit to catalog</Typography>
            <Alert severity="warning">
              This step applies validated rows to the product catalog. Unmapped columns marked &quot;staged metadata&quot; are
              merged under each SKU after upsert.
            </Alert>
            {selectedTemplate.destructive_apply_requires_confirm ? (
              <FormControlLabel
                control={<Checkbox checked={confirmDestructive} onChange={(_, c) => setConfirmDestructive(c)} />}
                label="I confirm applying this Product Master import (required by template policy)."
              />
            ) : null}
            {commitPm.isError ? (
              <Alert severity="error">{safeDisplayError(commitPm.error)}</Alert>
            ) : null}
            {pmJobState?.status === 'commit_queued' || pmJobState?.status === 'commit_running' ? (
              <Alert severity="info">
                Background commit in progress. You can leave or refresh this page — job <strong>#{lastJobId}</strong> will
                keep updating in the jobs grid and in the status panel above.
              </Alert>
            ) : null}
            {pmJobState?.status === 'commit_failed' ? (
              <Alert severity="error">
                {pmJobState.error_summary ??
                  'Commit failed. Review import row messages, fix the source or mapping, then try Commit again.'}
              </Alert>
            ) : null}
            {pmJobState?.stage === 'pm_committed' ? (
              <Alert severity="success">Commit finished successfully. This import is applied to the catalog.</Alert>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(5)}>Back</Button>
              <Button
                variant="contained"
                color="primary"
                disabled={
                  pmJobState?.validation_passed !== true ||
                  commitPm.isPending ||
                  pmJobState?.status === 'commit_queued' ||
                  pmJobState?.status === 'commit_running' ||
                  pmJobState?.stage === 'pm_committed' ||
                  (selectedTemplate.destructive_apply_requires_confirm && !confirmDestructive)
                }
                onClick={() => void commitPm.mutateAsync()}
              >
                {pmJobState?.status === 'commit_queued' || pmJobState?.status === 'commit_running'
                  ? 'Commit in progress…'
                  : pmJobState?.stage === 'pm_committed'
                    ? 'Committed'
                    : 'Commit / apply'}
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 4 && isDsi && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="body2">
              Upload for <strong>{selectedTemplate.display_name}</strong> using provider{' '}
              <strong>{(sources ?? []).find((s) => s.id === sourceId)?.name ?? '—'}</strong>. Headers are detected
              automatically; map them to business fields in the next step (you do not need to rename columns like DISTI in
              the file).
            </Typography>
            {!canGoUpload ? <Alert severity="warning">Complete provider, mode, and confirmations before uploading.</Alert> : null}
            <Box
              onDragEnter={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                const f = e.dataTransfer.files?.[0];
                onFile(f);
              }}
              sx={{
                border: '2px dashed',
                borderColor: dragActive ? 'primary.main' : 'divider',
                borderRadius: 2,
                px: 3,
                py: 4,
                textAlign: 'center',
                bgcolor: dragActive ? 'action.selected' : 'action.hover',
              }}
            >
              <CloudUploadOutlinedIcon sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <Typography variant="subtitle1" fontWeight={600}>
                Drop CSV or XLSX here
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Or choose a file. Validation and apply run only after you confirm mappings.
              </Typography>
              <Button variant="contained" component="label" disabled={!canGoUpload || upload.isPending}>
                Choose file
                <input
                  hidden
                  type="file"
                  accept=".csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(e) => {
                    onFile(e.target.files?.[0]);
                    e.target.value = '';
                  }}
                />
              </Button>
            </Box>
            {upload.isPending ? <LinearProgress /> : null}
            {upload.isError ? <Alert severity="error">{safeDisplayError(upload.error)}</Alert> : null}
            {upload.isSuccess && lastJobId != null ? (
              <Alert severity="success" data-testid="dsi-upload-success">
                Job <strong>#{lastJobId}</strong> created. Continue to column mapping.
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(3)}>Back</Button>
              <Button variant="contained" disabled={lastJobId == null} onClick={() => setActiveStep(5)}>
                Next: column mapping
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 5 && isDsi && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Map file columns → business fields</Typography>
            <Alert severity="info" data-testid="dsi-customer-field-mapping-hint">
              <Typography variant="body2" fontWeight={600} display="block" gutterBottom>
                Customer fields (e.g. RAW workbooks)
              </Typography>
              <Typography variant="body2" display="block">
                Map <strong>Dealer Name Group</strong> to <strong>Customer account</strong> — the account used for
                reporting, matching, and facts. Map <strong>Customer name</strong> to <strong>Source customer name</strong>{' '}
                — the name from the file, kept as alias / evidence for matching.
              </Typography>
            </Alert>
            {dsiJobFailedAlert}
            <Alert severity="info" data-testid="dsi-mapping-missing-vs-unresolved">
              <strong>Missing mapping</strong> means no file column is linked to a required field.{' '}
              <strong>Unresolved value</strong> means a column is mapped but a token (for example a distributor name) is not
              found in master data — fix master data or aliases; you do not need to rename source headers like DISTI.
            </Alert>
            {!dsiMappingState?.file_headers?.length ? (
              <Alert severity="warning">Loading column headers…</Alert>
            ) : null}
            {dsiMappingState?.blocking_mapping_errors?.length ? (
              <Alert severity="warning">
                {dsiMappingState.blocking_mapping_errors.map((e) => (
                  <Typography key={e.code} variant="body2" display="block">
                    {e.message}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {dsiMappingState?.mapping_adjustment_notices?.length ? (
              <Alert severity="info" data-testid="dsi-mapping-adjustments">
                <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                  Mapping adjustments
                </Typography>
                {dsiMappingState.mapping_adjustment_notices.map((n, i) => (
                  <Typography key={`${n.code}-${i}`} variant="caption" display="block" color="text.secondary">
                    {n.message}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            <Table size="small" data-testid="dsi-mapping-table">
              <TableHead>
                <TableRow>
                  <TableCell>File column</TableCell>
                  <TableCell sx={{ minWidth: 280 }}>Maps to</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(dsiMappingState?.file_headers ?? []).map((h) => (
                  <TableRow key={h}>
                    <TableCell>
                      <Typography fontWeight={600}>{h}</Typography>
                      <Typography variant="caption" color="text.secondary" display="block" data-testid={`dsi-samples-${h}`}>
                        Examples: {formatDsiSamples(dsiMappingState?.column_samples?.[h])}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Auto: {dsiMappingState?.field_mapping?.[h] ? dsiTargetLabel(dsiMappingState.field_mapping[h]) : '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <FormControl size="small" fullWidth>
                        <InputLabel id={`dsi-map-${h}`}>Target</InputLabel>
                        <Select
                          labelId={`dsi-map-${h}`}
                          label="Target"
                          value={dsiSelectValue(dsiMapDraft[h], dsiCanonSet)}
                          displayEmpty
                          renderValue={(selected) => {
                            const v = String(selected ?? '');
                            if (!v) return <em>— Unmapped —</em>;
                            return dsiTargetLabel(v);
                          }}
                          onChange={(e) => {
                            const v = e.target.value as string;
                            setDsiMapDraft((prev) => {
                              const next = { ...prev };
                              if (!v) delete next[h];
                              else next[h] = v;
                              return next;
                            });
                          }}
                        >
                          <MenuItem value="">
                            <em>— Unmapped —</em>
                          </MenuItem>
                          {(dsiMappingState?.canonical_targets ?? []).map((t) => (
                            <MenuItem key={t} value={t} sx={{ alignItems: 'flex-start', whiteSpace: 'normal' }}>
                              <ListItemText
                                primary={dsiTargetLabel(t)}
                                secondary={dsiTargetDescription(t)}
                                primaryTypographyProps={{ variant: 'body2' }}
                                secondaryTypographyProps={{ variant: 'caption', color: 'text.secondary' }}
                              />
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button onClick={() => setActiveStep(4)}>Back</Button>
              <Button
                variant="outlined"
                disabled={!dsiGateOk || saveDsiMapping.isPending}
                onClick={() => void saveDsiMapping.mutateAsync()}
              >
                Save mapping
              </Button>
              <Button
                variant="contained"
                disabled={!dsiGateOk || saveDsiMapping.isPending}
                onClick={() =>
                  void saveDsiMapping.mutateAsync().then(() => {
                    void refetchDsiMapping();
                    setActiveStep(6);
                  })
                }
              >
                Save & continue to validate
              </Button>
            </Stack>
            {saveDsiMapping.isError ? <Alert severity="error">{safeDisplayError(saveDsiMapping.error)}</Alert> : null}
          </Stack>
        ) : null}

        {activeStep === 6 && isDsi && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Validate (no fact writes)</Typography>
            {dsiJobFailedAlert}
            {!dsiServerMappingGateOk ? (
              <Alert severity="warning" data-testid="dsi-validate-blocked">
                Complete required column mappings on the previous step, then use <strong>Save mapping</strong> or{' '}
                <strong>Save &amp; continue to validate</strong> before running validation.
              </Alert>
            ) : null}
            {dsiValidate.isPending ? <LinearProgress /> : null}
            {dsiValidate.isError ? <Alert severity="error">{safeDisplayError(dsiValidate.error)}</Alert> : null}
            {dsiValidate.isSuccess ? (
              <Alert
                severity={
                  distributorSiSummary != null && (distributorSiSummary.blocking_rows ?? 0) > 0
                    ? 'warning'
                    : distributorSiSummary != null &&
                        ((distributorSiSummary.warning_rows ?? 0) > 0 ||
                          (distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0)
                      ? 'warning'
                      : 'success'
                }
                data-testid="dsi-validate-finished"
              >
                {distributorSiSummary != null && (distributorSiSummary.blocking_rows ?? 0) > 0 ? (
                  'Validation finished with blocking issues. Fix mappings or source data, then re-run validation before applying.'
                ) : distributorSiSummary != null &&
                  ((distributorSiSummary.warning_rows ?? 0) > 0 ||
                    (distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0) ? (
                  <>
                    Validation finished without blocking distributor/product errors. Some rows still have warnings
                    (including possible sell-out customer or transaction-date issues).{' '}
                    {(distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0 ? (
                      <>
                        <strong>{distributorSiSummary.rows_inventory_ready_with_sellout_warnings}</strong> row(s) have
                        valid distributor inventory (stock snapshot) but incomplete sell-out — applying may still upsert
                        inventory facts while leaving sell-out unresolved for those rows unless you fix mappings or
                        aliases first.{' '}
                      </>
                    ) : null}
                    Review row diagnostics and mapping candidates before applying.
                  </>
                ) : (
                  'Validation finished. Review the summary and row diagnostics below.'
                )}
              </Alert>
            ) : null}
            {lastJobId != null && distributorSiSummary ? (
              <Alert severity="info" data-testid="dsi-preview-summary">
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  Import summary: {distributorSiSummary.staging_rows ?? '—'} rows processed;{' '}
                  <strong>{distributorSiSummary.blocking_rows ?? 0}</strong> blocking;{' '}
                  <strong>{distributorSiSummary.warning_rows ?? 0}</strong> warnings;{' '}
                  <strong>{distributorSiSummary.aggregated_candidates ?? 0}</strong> aggregated mapping candidate groups.
                </Typography>
                {dsiCandidates != null && dsiCandidates.length > 0 ? (
                  <Typography variant="caption" color="text.secondary" display="block">
                    Resolve grouped tokens below on this page, or open the full grid in the global{' '}
                    <Link component={NextLink} href={`/admin/mappings?import_job_id=${lastJobId}`}>
                      Mapping queue
                    </Link>{' '}
                    ({dsiCandidates.length} group{dsiCandidates.length !== 1 ? 's' : ''} for this job).
                  </Typography>
                ) : null}
                {(distributorSiSummary.warning_rows ?? 0) > 0 ||
                (distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0 ? (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    Warnings do not block Continue to apply when there are zero blocking rows — inventory may still load
                    where the file has valid stock snapshots even if some sell-out lines are incomplete.
                  </Typography>
                ) : null}
              </Alert>
            ) : null}
            {lastJobId != null && dsiCandidates != null && dsiCandidates.length > 0 ? (
              <DsiImportJobResolutionSection
                importJobId={lastJobId}
                candidates={dsiCandidates}
                onInvalidate={() => void refetchPreview()}
              />
            ) : null}
            {previewRows && previewRows.length > 0 ? (
              <Table size="small" data-testid="dsi-validate-rows">
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Code</TableCell>
                    <TableCell>Message</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewRows.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.row_number}</TableCell>
                      <TableCell>{r.severity}</TableCell>
                      <TableCell>{r.code}</TableCell>
                      <TableCell>{r.message}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              <Button onClick={() => setActiveStep(5)} disabled={dsiValidate.isPending}>
                Back
              </Button>
              {dsiCanContinueToApply ? (
                <>
                  <Button
                    variant="outlined"
                    onClick={() => void dsiValidate.mutateAsync()}
                    disabled={dsiValidate.isPending || !dsiServerMappingGateOk}
                    data-testid="dsi-rerun-validation"
                  >
                    {dsiValidate.isPending ? 'Validating…' : 'Re-run validation'}
                  </Button>
                  <Button variant="contained" onClick={() => setActiveStep(7)} data-testid="dsi-continue-to-apply">
                    Continue to apply
                  </Button>
                </>
              ) : (
                <Button
                  variant="contained"
                  onClick={() => void dsiValidate.mutateAsync()}
                  disabled={dsiValidate.isPending || !dsiServerMappingGateOk}
                  data-testid="dsi-run-validation"
                >
                  {dsiValidate.isPending ? 'Validating…' : dsiHasValidateResult ? 'Re-run validation' : 'Run validation'}
                </Button>
              )}
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 7 && isDsi && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Apply to canonical facts (upsert)</Typography>
            {dsiJobFailedAlert}
            <Alert severity="warning">
              Apply upserts sell-out and distributor inventory using natural keys (distributor + customer + product + period
              for sell-out; distributor + product + snapshot date for inventory). Re-uploading overlapping history updates
              existing facts instead of duplicating them.
            </Alert>
            {distributorSiSummary != null &&
            ((distributorSiSummary.warning_rows ?? 0) > 0 ||
              (distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0) ? (
              <Alert severity="warning" data-testid="dsi-apply-sellout-warning-reminder">
                This job&apos;s last validation reported warnings. Sell-out may be incomplete for some rows while
                inventory may still apply where stock snapshots are valid. Confirm mappings and aliases before applying.
                {(distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0 ? (
                  <>
                    {' '}
                    <strong>{distributorSiSummary.rows_inventory_ready_with_sellout_warnings}</strong> row(s) matched the
                    &quot;inventory ready but sell-out blocked&quot; pattern.
                  </>
                ) : null}
              </Alert>
            ) : null}
            {selectedTemplate.destructive_apply_requires_confirm ? (
              <FormControlLabel
                control={<Checkbox checked={confirmDestructive} onChange={(_, c) => setConfirmDestructive(c)} />}
                label="I confirm applying this distributor sales & inventory import."
              />
            ) : null}
            {dsiApply.isError ? <Alert severity="error">{safeDisplayError(dsiApply.error)}</Alert> : null}
            {dsiApply.isPending ? <LinearProgress /> : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(6)}>Back</Button>
              <Button
                variant="contained"
                color="primary"
                disabled={
                  dsiApply.isPending ||
                  (selectedTemplate.destructive_apply_requires_confirm && !confirmDestructive)
                }
                onClick={() => void dsiApply.mutateAsync()}
              >
                Apply
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {(activeStep === 4 && !isPm && !isDsi && !isShipmentEvidence) ||
        (activeStep === 3 && isShipmentEvidence && !isPm && !isDsi) ? (
          <Stack spacing={2}>
            {isShipmentEvidence ? (
              <Alert severity="info">
                This upload runs in validate mode only. When column mapping is ready, map file columns below, save, run
                validation, then resolve distributors and click Apply import to set loaded.
              </Alert>
            ) : null}
            <Typography variant="body2">
              Upload for <strong>{selectedTemplate?.display_name}</strong> using provider{' '}
              <strong>{(sources ?? []).find((s) => s.id === sourceId)?.name ?? '—'}</strong>.
            </Typography>
            {isJobRevisitMode && lastJobId != null ? (
              <Alert severity="info" data-testid="revisit-banner">
                Viewing diagnostics for job <strong>#{lastJobId}</strong> in read-only mode. Upload a new file above to
                run a fresh import.
              </Alert>
            ) : null}
            {!canGoUpload && !isJobRevisitMode ? (
              <Alert severity="warning">Complete provider, mode, and confirmations before uploading.</Alert>
            ) : null}
            <Box
              onDragEnter={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                const f = e.dataTransfer.files?.[0];
                onFile(f);
              }}
              sx={{
                border: '2px dashed',
                borderColor: dragActive ? 'primary.main' : 'divider',
                borderRadius: 2,
                px: 3,
                py: 4,
                textAlign: 'center',
                bgcolor: dragActive ? 'action.selected' : 'action.hover',
              }}
            >
              <CloudUploadOutlinedIcon sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <Typography variant="subtitle1" fontWeight={600}>
                Drop CSV or XLSX here
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Or choose a file. Pipeline runs according to import mode.
              </Typography>
              <Button variant="contained" component="label" disabled={!canGoUpload || upload.isPending}>
                Choose file
                <input
                  hidden
                  type="file"
                  accept=".csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(e) => {
                    onFile(e.target.files?.[0]);
                    e.target.value = '';
                  }}
                />
              </Button>
            </Box>
            {upload.isPending ? <LinearProgress /> : null}
            {upload.isError ? (
              <Alert severity="error">{safeDisplayError(upload.error)}</Alert>
            ) : null}
            {upload.isSuccess && lastJobId != null && upload.data?.import_mode !== 'apply' ? (
              <Alert severity="success">
                Job <strong>#{lastJobId}</strong> created.{' '}
                <Button size="small" onClick={() => void refetchPreview()}>
                  Refresh validation preview
                </Button>
              </Alert>
            ) : null}
            {(shipmentEvidenceUrlUnlock || isShipmentEvidence) &&
            shipmentEvidencePollJobId != null &&
            shipmentEvidenceJobPollUnlocked &&
            shipmentImportJob &&
            (shipmentImportJob.stage || '').trim() === 'shipment_mapping_ready' ? (
              <Stack spacing={1.5} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 2 }}>
                <Typography variant="subtitle2" fontWeight={600}>
                  Column mapping (required before validation)
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Map each file column to a canonical shipment field. Save your mapping, then run validation (same flow as
                  distributor sales & inventory mapping).
                </Typography>
                {shipmentMappingStateQueryError ? (
                  <Alert severity="error">{safeDisplayError(shipmentMappingStateQueryErr)}</Alert>
                ) : null}
                {shipmentMappingStateLoading ? <LinearProgress /> : null}
                {!shipmentMappingStateLoading && shipmentMappingState?.file_headers?.length ? (
                  <>
                    {shipmentMappingState.blocking_mapping_errors?.length ? (
                      <Alert severity="error">
                        <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                          Fix mapping before validating
                        </Typography>
                        <Stack component="ul" sx={{ m: 0, pl: 2 }}>
                          {shipmentMappingState.blocking_mapping_errors.map((e) => (
                            <Typography key={e.code} component="li" variant="body2">
                              {e.message}
                            </Typography>
                          ))}
                        </Stack>
                      </Alert>
                    ) : null}
                    {shipmentMappingState.mapping_adjustment_notices?.length ? (
                      <Alert severity="info">
                        {shipmentMappingState.mapping_adjustment_notices.map((n) => (
                          <Typography key={n.code ?? n.message} variant="body2">
                            {n.message}
                          </Typography>
                        ))}
                      </Alert>
                    ) : null}
                    {shipmentMappingDraftDirty ? (
                      <Alert severity="warning">You have unsaved mapping changes. Save before running validation.</Alert>
                    ) : null}
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600 }}>File column</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Maps to</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {shipmentMappingState.file_headers.map((h) => (
                          <TableRow key={h}>
                            <TableCell>
                              <Typography fontWeight={600}>{h}</Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                display="block"
                                data-testid={`shipment-samples-${h}`}
                              >
                                Examples: {formatDsiSamples(shipmentMappingState.column_samples?.[h])}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <FormControl size="small" fullWidth>
                                <InputLabel id={`shipment-map-${h}`}>Target</InputLabel>
                                <Select
                                  labelId={`shipment-map-${h}`}
                                  label="Target"
                                  value={shipmentMapDraft[h] ?? ''}
                                  displayEmpty
                                  renderValue={(selected) => {
                                    const v = String(selected ?? '');
                                    if (!v) return <em>— Unmapped —</em>;
                                    return SHIPMENT_FIELD_LABELS[v] ?? v;
                                  }}
                                  onChange={(e) => {
                                    const v = e.target.value as string;
                                    setShipmentMapDraft((prev) => {
                                      const next = { ...prev };
                                      if (!v) delete next[h];
                                      else next[h] = v;
                                      return next;
                                    });
                                  }}
                                >
                                  <MenuItem value="">
                                    <em>— Unmapped —</em>
                                  </MenuItem>
                                  {(shipmentMappingState.canonical_targets ?? []).map((t) => (
                                    <MenuItem key={t} value={t} sx={{ alignItems: 'flex-start', whiteSpace: 'normal' }}>
                                      <ListItemText
                                        primary={SHIPMENT_FIELD_LABELS[t] ?? t}
                                        secondary={shipmentMappingState.field_target_descriptions?.[t]}
                                        primaryTypographyProps={{ variant: 'body2' }}
                                        secondaryTypographyProps={{ variant: 'caption', color: 'text.secondary' }}
                                      />
                                    </MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                      <Button
                        variant="outlined"
                        disabled={
                          saveShipmentMapping.isPending ||
                          !shipmentMappingState.file_headers.length ||
                          isJobRevisitMode
                        }
                        onClick={() => void saveShipmentMapping.mutateAsync()}
                      >
                        {saveShipmentMapping.isPending ? 'Saving…' : 'Save mapping'}
                      </Button>
                      <Button
                        variant="contained"
                        disabled={
                          shipmentValidateRun.isPending ||
                          saveShipmentMapping.isPending ||
                          !shipmentMappingState.file_headers.length ||
                          shipmentMappingDraftDirty ||
                          !shipmentMappingState.mapping_valid ||
                          isJobRevisitMode
                        }
                        onClick={() => void shipmentValidateRun.mutateAsync()}
                      >
                        {shipmentValidateRun.isPending ? 'Validating…' : 'Run validation'}
                      </Button>
                    </Stack>
                    {saveShipmentMapping.isError ? (
                      <Alert severity="error">{safeDisplayError(saveShipmentMapping.error)}</Alert>
                    ) : null}
                    {shipmentValidateRun.isError ? (
                      <Alert severity="error">{safeDisplayError(shipmentValidateRun.error)}</Alert>
                    ) : null}
                  </>
                ) : !shipmentMappingStateLoading && !shipmentMappingStateQueryError ? (
                  <Typography variant="body2" color="text.secondary">
                    Waiting for inferred columns…
                  </Typography>
                ) : null}
              </Stack>
            ) : null}
            {(shipmentEvidenceUrlUnlock || isShipmentEvidence) &&
            shipmentEvidencePollJobId != null &&
            shipmentEvidenceJobPollUnlocked &&
            shipmentImportJob &&
            ['validated', 'loaded'].includes((shipmentImportJob.stage || '').trim()) ? (
              <ShipmentEntityStewardPanel importJobId={shipmentEvidencePollJobId} />
            ) : null}
            {(shipmentEvidenceUrlUnlock || isShipmentEvidence) &&
            shipmentEvidencePollJobId != null &&
            shipmentEvidenceJobPollUnlocked &&
            shipmentImportJob?.stage === 'validated' ? (
              <Stack spacing={1}>
                <Button
                  variant="contained"
                  color="primary"
                  size="large"
                  disabled={shipmentApplyMut.isPending}
                  onClick={() => void shipmentApplyMut.mutateAsync()}
                >
                  Apply import
                </Button>
                {shipmentApplyMut.isError ? (
                  <Alert severity="error">{safeDisplayError(shipmentApplyMut.error)}</Alert>
                ) : null}
              </Stack>
            ) : null}
            {isShipmentEvidence && shipmentApplyWarning ? (
              <Alert severity="warning" onClose={() => setShipmentApplyWarning(null)}>
                {shipmentApplyWarning}
              </Alert>
            ) : null}
            {selectedTemplate?.slug === 'historical_lineup' && historicalValidatedJobId != null && hlSheetDetail ? (
              <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: showMappingReview ? 1 : 0 }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    Column mapping review — Sheet: {hlSheetDetail.sheet_name}
                  </Typography>
                  <Chip
                    size="small"
                    label={`Confidence: ${Math.round(hlSheetDetail.mapping_confidence * 100)}%`}
                    color={hlSheetDetail.mapping_confidence >= 0.5 ? 'success' : 'warning'}
                    variant="outlined"
                  />
                  <Button
                    size="small"
                    variant="text"
                    sx={{ ml: 'auto' }}
                    onClick={() => setShowMappingReview((v) => !v)}
                  >
                    {showMappingReview ? 'Hide' : 'Show / edit'}
                  </Button>
                </Stack>
                {showMappingReview ? (
                  <Stack spacing={1}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600 }}>Field</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Detected column</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Override</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {HL_MAPPING_DISPLAY_FIELDS.map(({ canonical, label }) => (
                          <TableRow key={canonical}>
                            <TableCell>{label}</TableCell>
                            <TableCell>
                              <Typography variant="caption" color={hlDetectedMapping[canonical] ? 'text.primary' : 'text.disabled'}>
                                {hlDetectedMapping[canonical] ?? '— not detected'}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <FormControl size="small" sx={{ minWidth: 160 }}>
                                <Select
                                  displayEmpty
                                  value={hlMappingEdits[hlSheetDetail.sheet_name]?.[canonical] ?? ''}
                                  onChange={(e) => {
                                    const val = e.target.value as string;
                                    setHlMappingEdits((prev) => {
                                      const sheetEdits = { ...prev[hlSheetDetail.sheet_name] };
                                      if (val === '') {
                                        delete sheetEdits[canonical];
                                      } else {
                                        sheetEdits[canonical] = val;
                                      }
                                      const next = { ...prev, [hlSheetDetail.sheet_name]: sheetEdits };
                                      if (Object.keys(next[hlSheetDetail.sheet_name]).length === 0) {
                                        const { [hlSheetDetail.sheet_name]: _removed, ...rest } = next;
                                        return rest;
                                      }
                                      return next;
                                    });
                                  }}
                                  renderValue={(v) => (v === '' ? <em style={{ color: '#999' }}>use detected</em> : v)}
                                >
                                  <MenuItem value=""><em>— use detected —</em></MenuItem>
                                  {hlSourceColumns.map((col) => (
                                    <MenuItem key={col} value={col}>{col}</MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    {hlHasEdits && lastGenericFile ? (
                      <Box>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={upload.isPending}
                          onClick={() =>
                            upload.mutate({
                              file: lastGenericFile,
                              modeOverride: 'validate',
                              mappingOverride: hlMappingEdits,
                            })
                          }
                        >
                          Re-validate with corrections
                        </Button>
                      </Box>
                    ) : null}
                  </Stack>
                ) : null}
              </Box>
            ) : null}
            {qualityReview && historicalValidatedJobId != null ? (
              <Box
                data-testid="quality-review-panel"
                sx={{
                  border: '1px solid',
                  borderColor: qualityReview.isApplyReady ? 'success.light' : 'warning.light',
                  borderRadius: 1,
                  p: 1.5,
                }}
              >
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography
                      variant="caption"
                      fontWeight={700}
                      color={qualityReview.isApplyReady ? 'success.main' : 'error.main'}
                      data-testid="quality-review-badge"
                    >
                      {qualityReview.isApplyReady
                        ? '✓ Apply ready'
                        : `✗ ${qualityReview.blockingCount} blocking error${qualityReview.blockingCount !== 1 ? 's' : ''}`}
                    </Typography>
                    {qualityReview.okCount > 0 && (
                      <Chip size="small" label={`${qualityReview.okCount} accepted`} color="success" variant="outlined" />
                    )}
                    {qualityReview.commercialWarningCount > 0 && (
                      <Chip
                        size="small"
                        label={`${qualityReview.commercialWarningCount} commercial warning${qualityReview.commercialWarningCount !== 1 ? 's' : ''}`}
                        color="warning"
                        variant="outlined"
                      />
                    )}
                  </Stack>

                  {qualityReview.unknownCustomerCount > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block' }}>
                        Unresolved customers — {qualityReview.unknownCustomerRowCount} row
                        {qualityReview.unknownCustomerRowCount !== 1 ? 's' : ''},{' '}
                        {qualityReview.unknownCustomerCount} distinct token
                        {qualityReview.unknownCustomerCount !== 1 ? 's' : ''}
                      </Typography>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                        {Array.from(qualityReview.unknownCustomerTokens.entries())
                          .slice(0, 10)
                          .map(([token, count]) => (
                            <Chip
                              key={token}
                              size="small"
                              label={`${token} (${count})`}
                              color="warning"
                              variant="outlined"
                            />
                          ))}
                      </Stack>
                      <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 0.5 }}>
                        Rows will be saved with null customer FK. Map tokens to customers in a later step.
                      </Typography>
                    </Box>
                  )}

                  {qualityReview.invalidNumericExamples.length > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block' }}>
                        Invalid numeric fields — examples:
                      </Typography>
                      <Typography variant="caption" color="text.disabled">
                        {qualityReview.invalidNumericExamples.join(' · ')}
                      </Typography>
                    </Box>
                  )}
                </Stack>
              </Box>
            ) : null}
            {selectedTemplate?.slug === 'historical_lineup' && historicalValidatedJobId != null && lastGenericFile ? (
              hlShowApplyConfirm ? (
                <Alert severity="warning" data-testid="apply-confirm-alert">
                  <Stack spacing={1}>
                    <Typography variant="body2">
                      {qualityReview?.unknownCustomerRowCount ?? 0} row
                      {(qualityReview?.unknownCustomerRowCount ?? 0) !== 1 ? 's' : ''} will be saved with unknown
                      customer (null FK). Proceed?
                    </Typography>
                    <Stack direction="row" spacing={1}>
                      <Button
                        size="small"
                        variant="contained"
                        color="warning"
                        disabled={upload.isPending}
                        onClick={() => {
                          setHlShowApplyConfirm(false);
                          upload.mutate({
                            file: lastGenericFile,
                            modeOverride: 'apply',
                            mappingOverride: hlHasEdits ? hlMappingEdits : undefined,
                          });
                        }}
                      >
                        Apply anyway
                      </Button>
                      <Button size="small" variant="text" onClick={() => setHlShowApplyConfirm(false)}>
                        Cancel
                      </Button>
                    </Stack>
                  </Stack>
                </Alert>
              ) : (
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    Validation job #{historicalValidatedJobId} completed. Apply requires an explicit second click.
                  </Typography>
                  <Button
                    size="small"
                    variant="contained"
                    disabled={upload.isPending || (qualityReview != null && !qualityReview.isApplyReady)}
                    onClick={() => {
                      if (qualityReview?.unknownCustomerCount && qualityReview.unknownCustomerCount > 0) {
                        setHlShowApplyConfirm(true);
                      } else {
                        upload.mutate({
                          file: lastGenericFile,
                          modeOverride: 'apply',
                          mappingOverride: hlHasEdits ? hlMappingEdits : undefined,
                        });
                      }
                    }}
                  >
                    Apply validated file
                  </Button>
                </Stack>
              )
            ) : null}
            {upload.isSuccess && lastJobId != null && upload.data?.import_mode === 'apply' ? (
              <Alert severity="success" data-testid="apply-success-alert">
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <span>
                    Apply job <strong>#{lastJobId}</strong> completed. Row diagnostics are shown below.
                  </span>
                  <Link
                    component={NextLink}
                    href={`/admin/imports?job=${lastJobId}`}
                    data-testid="view-apply-job-link"
                    sx={{ whiteSpace: 'nowrap' }}
                  >
                    View apply job →
                  </Link>
                </Stack>
              </Alert>
            ) : null}
            {hlApplyJobId != null && selectedSlug === 'historical_lineup' ? (
              <Box
                data-testid="loaded-lineup-section"
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}
              >
                <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                  Loaded lineup data — {lineupLines?.length ?? '…'} line{lineupLines?.length !== 1 ? 's' : ''}
                </Typography>
                {unresolvedCustomerTokens.size > 0 ? (
                  <Box data-testid="lineup-unresolved-tokens" sx={{ mb: 1.5 }}>
                    <Typography variant="caption" fontWeight={600} color="warning.main" sx={{ display: 'block', mb: 0.5 }}>
                      Unresolved customer tokens —{' '}
                      {unresolvedCustomerTokens.size} distinct,{' '}
                      {Array.from(unresolvedCustomerTokens.values()).reduce((a, b) => a + b, 0)} rows
                    </Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {Array.from(unresolvedCustomerTokens.entries()).map(([token, count]) => (
                        <Chip key={token} size="small" label={`${token} (${count})`} color="warning" variant="outlined" />
                      ))}
                    </Stack>
                  </Box>
                ) : null}
                {lineupLines && lineupLines.length > 0 ? (
                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small" sx={{ minWidth: 700 }}>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600 }}>Row</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Product ID</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Part #</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Model</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Base Unit</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Customer ID</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Qty</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>MSRP</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Promo</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>DAP</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Disti Margin %</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {lineupLines.map((ln) => (
                          <TableRow key={ln.id}>
                            <TableCell>{ln.source_row_number}</TableCell>
                            <TableCell>{ln.product_id ?? <em style={{ color: '#999' }}>—</em>}</TableCell>
                            <TableCell>{ln.part_number_raw ?? '—'}</TableCell>
                            <TableCell>{ln.model_raw ?? '—'}</TableCell>
                            <TableCell>{ln.base_unit_raw ?? '—'}</TableCell>
                            <TableCell>{ln.header_customer_id ?? <em style={{ color: '#999' }}>—</em>}</TableCell>
                            <TableCell>{ln.quantity_units ?? '—'}</TableCell>
                            <TableCell>{ln.msrp_local ?? '—'}</TableCell>
                            <TableCell>{ln.promo_price_local ?? '—'}</TableCell>
                            <TableCell>{ln.dap_local ?? '—'}</TableCell>
                            <TableCell>
                              {ln.disti_margin_pct != null ? `${ln.disti_margin_pct}%` : '—'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                ) : lineupLines ? (
                  <Typography variant="caption" color="text.disabled">
                    No lineup lines loaded for this job.
                  </Typography>
                ) : null}
              </Box>
            ) : null}
            {diagnosticSummary.length > 0 ? (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid="diagnostic-summary">
                <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center', mr: 0.5 }}>
                  Summary:
                </Typography>
                {diagnosticSummary.map(({ code, count }) => {
                  const color = HL_DIAGNOSTIC_ERROR_CODES.has(code)
                    ? 'error'
                    : code.includes('ok') || code.includes('summary') || code.includes('processed')
                      ? 'default'
                      : 'warning';
                  return (
                    <Chip
                      key={code}
                      size="small"
                      label={`${code} (${count})`}
                      color={color as 'error' | 'warning' | 'default'}
                      variant="outlined"
                    />
                  );
                })}
              </Stack>
            ) : null}
            {previewRows && previewRows.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Code</TableCell>
                    <TableCell>Message</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewRows.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.row_number}</TableCell>
                      <TableCell>{r.severity}</TableCell>
                      <TableCell>{r.code}</TableCell>
                      <TableCell>{r.message}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setActiveStep(isShipmentEvidence ? 2 : 3)}>Back</Button>
              <Button
                onClick={() => {
                  setActiveStep(0);
                  setSelectedSlug(null);
                  setSourceId('');
                  setLastJobId(null);
                  setLastGenericFile(null);
                  setHistoricalValidatedJobId(null);
                  setIsJobRevisitMode(false);
                  setHlMappingEdits({});
                  setShowMappingReview(false);
                  setHlShowApplyConfirm(false);
                  setLastApplyJobId(null);
                  upload.reset();
                  pmUpload.reset();
                  void router.replace('/admin/imports');
                }}
              >
                Start over
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Import jobs
        </Typography>
        <ModuleDataSection
          intro="Jobs include template slug and import mode. Product Master mapping jobs show stages pm_headers_ready → pm_mapping_saved → pm_validated → pm_committed."
          isLoading={jobsLoading}
          isError={jobsIsError}
          error={toQueryError(jobsErr)}
          onRetry={() => void refetchJobs()}
          isEmpty={jobsList.length === 0}
          empty={{
            title: 'No import jobs yet',
            description: 'Complete the guided import above, or use the API directly.',
            primary: { label: 'Mapping queue', href: '/admin/mappings' },
            secondary: { label: 'Getting started', href: '/getting-started' },
          }}
          toolbar={
            <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" useFlexGap sx={{ mb: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={showArchivedImportJobs}
                    onChange={(_, v) => setShowArchivedImportJobs(v)}
                    size="small"
                  />
                }
                label="Show archived"
              />
              <ModuleGridToolbar
                sx={{ mb: 0 }}
                onRefresh={() => void qc.invalidateQueries({ queryKey: ['import-jobs'] })}
              />
              <BulkSelectionToolbar
                mode={jobsBulkSelectionMode}
                selectedCount={jobsSelectedCount}
                visibleRowCount={jobsVisibleRowCount}
                onEnterSelectionMode={() => setJobsBulkSelectionMode('selecting')}
                onExitSelectionMode={() => setJobsBulkSelectionMode('normal')}
                onSelectAllVisible={() => {
                  const api = jobsGridApiRef.current;
                  if (!api) return;
                  api.forEachNodeAfterFilterAndSort((node) => {
                    if (node.data) node.setSelected(true);
                  });
                }}
                onDeselectAll={() => jobsGridApiRef.current?.deselectAll()}
                onPreviewDangerAction={() => void openImportJobBulkDeletePreview()}
                previewDangerDisabled={importJobBulkDeleteBusy}
                busy={importJobBulkDeleteBusy}
              />
            </Stack>
          }
        >
          <EnterpriseDataGrid
            key={jobsBulkSelectionMode === 'selecting' ? 'jobs-bulk' : 'jobs-normal'}
            rowData={jobsList}
            columnDefs={colDefs}
            height={420}
            gridOptions={jobsGridOptions}
          />
        </ModuleDataSection>
        <ImportJobBulkDeleteImpactDialog
          open={importJobBulkDeleteOpen}
          busy={importJobBulkDeleteBusy}
          preview={importJobBulkDeletePreview}
          deleteSemanticArtifacts={importJobDeleteSemanticArtifacts}
          onDeleteSemanticArtifactsChange={setImportJobDeleteSemanticArtifacts}
          impactAcknowledged={importJobBulkDeleteAck}
          onImpactAcknowledgedChange={setImportJobBulkDeleteAck}
          onClose={closeImportJobBulkDeleteDialog}
          onConfirm={() => void confirmImportJobBulkDelete()}
        />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          Line-up bulk upsert remains on the{' '}
          <Link component={NextLink} href="/lineup">
            Line-up planning
          </Link>{' '}
          screen; this wizard focuses on constrained file imports.
        </Typography>
      </Paper>
    </>
  );
}

export default function AdminImportsPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading imports workspace…</Typography>}>
      <AdminImportsPageContent />
    </Suspense>
  );
}

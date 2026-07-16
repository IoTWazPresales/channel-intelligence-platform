'use client';

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
  Tab,
  Tabs,
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
import {
  CanonicalColumnMappingPanel,
  type CanonicalRequiredGroup,
  type CanonicalTargetOption,
} from '@/features/import-mapping/CanonicalColumnMappingPanel';
import { apiGet, apiPost, apiUrl, readFetchError, safeDisplayError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import { ImportFileUploadZone } from './ImportFileUploadZone';
import { BulkLineupBackfillDialog } from './BulkLineupBackfillDialog';
import { DsiBulkUploadDialog } from './DsiBulkUploadDialog';
import { DsiCoveragePanel } from './DsiCoveragePanel';
import { DsiFileReviewStrip } from './DsiFileReviewStrip';
import { UnifiedLineupImportDialog } from './UnifiedLineupImportDialog';
import { PmImportProgressPanel, type PmProgressSnapshot } from './PmImportProgressPanel';
import {
  DSI_STEWARD_CONFIG,
  ImportJobLoadedSuccessCallout,
  importJobApplyIsLoaded,
  notifyDsiAsyncPipelineStarted,
  refetchDsiImportJobStewardQueries,
} from '@/features/import-steward';
import { deriveDsiJobDisplayState } from '@/features/import-steward/dsiJobDisplayState';
import {
  dsiJobHasValidationComplete,
  dsiWizardActiveStepFromServer,
} from '@/features/import-steward/dsiImportWizardRouting';
import {
  shipmentJobHasValidationComplete,
  shipmentPipelineInFlight as shipmentJobPipelineInFlight,
  shipmentWizardActiveStepFromServer,
} from '@/features/import-steward/shipmentImportWizardRouting';

import { useImportJobProgressQuery } from '@/features/background-tasks/useImportJobProgressQuery';

import { DsiImportJobResolutionSection } from './DsiImportJobResolutionSection';
import { DsiIntelligenceStatusPanel, type DsiIntelligenceState } from './DsiIntelligenceStatusPanel';
import { DsiValidateProgressPanel } from './DsiValidateProgressPanel';
import type { DsiValidateProgress } from './DsiValidateProgressPanel';
import type { DsiCandidateRow } from '../mappings/DsiCandidateStewardPanel';
import {
  computeDsiContinueGateKey,
  dsiContinueToApplyAllowed,
  dsiGateFromMapping,
  dsiGateFromNestedMapping,
  dsiHumanFixableBlockingRows,
  dsiSelectValue,
  dsiTargetDescription,
  dsiTargetLabel,
  formatDsiBlockerSummaryLine,
  isNestedDsiFieldMapping,
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
  hidden?: boolean;
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
  staged_metadata?: Record<string, unknown> | null;
};

type ImportJobsListResponse = {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

function normalizeImportJobsList(payload: ImportJobsListResponse | Job[]): Job[] {
  return Array.isArray(payload) ? payload : payload.items;
}

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
  staged_row_count?: number;
  /** Present after infer; includes dtype + first-row samples per column (JSON-safe). */
  inferred_schema?: { row_count: number; columns: InferredColumn[] } | null;
  /** Server-derived progress (counts, rail, phase); refreshed while validate/commit run. */
  progress?: PmProgressSnapshot | null;
};

/** Map PM server job state to wizard step indices (stepsPm: 3 upload … 6 commit). */
function pmWizardActiveStepFromServer(state: {
  stage: string;
  status: string;
  validation_passed: boolean | null;
  progress?: PmProgressSnapshot | null;
}): number | null {
  const stage = (state.stage || '').trim();
  const status = (state.status || '').trim();
  const phaseId = (state.progress?.phase_id || '').trim();

  if (
    status === 'commit_queued' ||
    status === 'commit_running' ||
    status === 'commit_failed' ||
    stage === 'pm_committed'
  ) {
    return 6;
  }
  if (stage === 'pm_validated') {
    return state.validation_passed === true ? 6 : 5;
  }
  if (
    status === 'validate_queued' ||
    status === 'validate_running' ||
    stage === 'pm_mapping_saved' ||
    phaseId === 'validate_pending' ||
    phaseId === 'validate_queued' ||
    phaseId === 'validate_running' ||
    phaseId === 'validate_failed'
  ) {
    return 5;
  }
  if (stage === 'pm_headers_ready' || phaseId === 'map') {
    return 4;
  }
  if (phaseId === 'upload' || stage === 'uploaded') {
    return 3;
  }
  return null;
}

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

const stepsShipmentEvidence = [
  'Import type',
  'Data provider',
  'Template details',
  'Upload file',
  'Column mapping',
  'Validate & resolve',
  'Apply',
];

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

/**
 * Live "still needs" requirements for inbound shipment mapping. Mirrors the server gate
 * in `shipment_mapping_gate_errors` so the summary chips match `blocking_mapping_errors`.
 */
const SHIPMENT_MAPPING_REQUIRED_GROUPS: CanonicalRequiredGroup[] = [
  { id: 'product', label: 'Product column', anyOf: ['item_code', 'ean_code', 'upc_code', 'sales_model_name'] },
  { id: 'distributor_party', label: 'Distributor party', anyOf: ['bill_to_raw', 'ship_to_raw', 'distributor_token'] },
];

/** Live "still needs" requirements for DSI mapping — mirrors `dsi_mapping_gate_errors`. */
const DSI_MAPPING_REQUIRED_GROUPS: CanonicalRequiredGroup[] = [
  { id: 'distributor', label: 'Distributor', anyOf: ['distributor_token'] },
  { id: 'product', label: 'Product identifier', anyOf: ['product_identifier'] },
  { id: 'date', label: 'Date', anyOf: ['transaction_date', 'snapshot_date'] },
  { id: 'quantity', label: 'Quantity or inventory', anyOf: ['quantity_sold', 'stock_on_hand'] },
];

/** Phase rail + copy for the inbound-shipment validate progress panel (reads `imports.process_job` progress). */
const SHIPMENT_PROGRESS_PHASES = [
  { id: 'processing_rows', label: 'Resolve rows' },
  { id: 'writing_shipment_lines', label: 'Write evidence' },
  { id: 'complete', label: 'Complete' },
] as const;

const SHIPMENT_PROGRESS_DESCRIPTIONS: Record<string, string> = {
  queued: 'Queued — waiting for the worker to pick up the task…',
  processing_rows: 'Parsing the file and resolving products & distributors in memory (no per-row DB scans).',
  writing_shipment_lines: 'Bulk-writing shipment evidence lines and building steward candidates.',
  complete: '',
  failed: '',
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
  const [unifiedLineupOpen, setUnifiedLineupOpen] = useState(false);
  const [bulkLineupBackfillOpen, setBulkLineupBackfillOpen] = useState(false);
  const [unifiedPeriodPrefill, setUnifiedPeriodPrefill] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | ''>('');
  const [importMode, setImportMode] = useState<'validate' | 'apply'>('validate');
  const [confirmDestructive, setConfirmDestructive] = useState(false);
  /** When a job exists, the large drop zone collapses; user can expand to start a new upload. */
  const [uploadZoneExpanded, setUploadZoneExpanded] = useState(false);
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
  const [dsiNestedMapDraft, setDsiNestedMapDraft] = useState<Record<string, Record<string, string>>>({});
  const [dsiActiveSheetKey, setDsiActiveSheetKey] = useState<string | null>(null);
  const [dsiBulkUploadOpen, setDsiBulkUploadOpen] = useState(false);
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
  const [shipmentValidateAsync, setShipmentValidateAsync] = useState(false);
  const [dsiValidateAsync, setDsiValidateAsync] = useState(false);
  // DSI apply runs async on the worker too. Tracked separately from validate because apply transits
  // through stage `validated` on its way to `loaded` — the validate poll would mis-read that
  // transient `validated` as "done", so apply needs its own poll terminal on `loaded`/`failed`.
  const [dsiApplyAsync, setDsiApplyAsync] = useState(false);
  const [dsiWorkflowMode, setDsiWorkflowMode] = useState<'auto' | 'historical' | 'weekly'>('auto');

  const openDsiHistoricalBackfill = useCallback(() => {
    setDsiWorkflowMode('historical');
    setActiveStep(4);
    setDsiBulkUploadOpen(true);
  }, []);

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
    // Exclude deferred slugs and any `hidden` template (e.g. `unified_lineup`, which has its own
    // dedicated Import-Centre card + dialog rather than the generic wizard).
    () => (templates ?? []).filter((t) => !DEFERRED_TEMPLATE_SLUGS.has(t.slug) && !t.hidden),
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

  // Deep-link from PO Management / gap worklist: ?unified=1&period=26Q1 opens the unified importer
  // with the period pre-filled.
  useEffect(() => {
    if (searchParams.get('unified') !== '1') return;
    setUnifiedPeriodPrefill(searchParams.get('period'));
    setUnifiedLineupOpen(true);
  }, [searchParams]);

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
    queryFn: async ({ signal }) => {
      const url = showArchivedImportJobs
        ? '/api/v1/imports/jobs?include_archived=true&limit=100'
        : '/api/v1/imports/jobs?limit=100';
      const payload = await apiGet<ImportJobsListResponse | Job[]>(url, { signal });
      return normalizeImportJobsList(payload);
    },
  });

  const importJobsListError = useMemo((): Error | null => {
    if (!jobsIsError) return null;
    const raw = toQueryError(jobsErr)?.message ?? '';
    if (
      /internal server error/i.test(raw) ||
      /\b500\b/.test(raw) ||
      /database temporarily unavailable/i.test(raw) ||
      /\b503\b/.test(raw) ||
      !raw.trim()
    ) {
      return new Error('Unable to load import jobs — please retry.');
    }
    return new Error(raw);
  }, [jobsIsError, jobsErr]);

  const { data: previewRows, refetch: refetchPreview } = useQuery({
    queryKey: ['import-job-rows', lastJobId],
    queryFn: ({ signal }) => apiGet<RowResult[]>(`/api/v1/imports/jobs/${lastJobId}/rows`, { signal }),
    enabled: lastJobId != null,
  });

  const {
    data: jobDetail,
    isError: jobDetailIsError,
    error: jobDetailErr,
    isFetched: jobDetailFetched,
  } = useQuery({
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
    if (jobIdParam == null) return;
    if (!jobDetail || !visibleTemplates.length) return;
    setLastJobId(jobDetail.id);
    setSelectedSlug(jobDetail.template_slug ?? null);
    setIsJobRevisitMode(true);
    if (jobDetail.template_slug === 'product_master') {
      setIsJobRevisitMode(false);
      const stage = (jobDetail.stage || '').trim();
      const status = (jobDetail.status || '').trim();
      if (status === 'validate_queued' || status === 'validate_running') {
        setActiveStep(5);
      } else if (status === 'commit_queued' || status === 'commit_running') {
        setActiveStep(6);
      } else if (stage === 'pm_committed') {
        setActiveStep(6);
      } else if (stage === 'pm_validated') {
        setActiveStep(5);
      } else if (stage === 'pm_mapping_saved') {
        setActiveStep(5);
      } else if (stage === 'pm_headers_ready') {
        setActiveStep(4);
      } else {
        setActiveStep(3);
      }
      return;
    }
    if (jobDetail.template_slug !== 'product_master') {
      if (jobDetail.template_slug === 'distributor_inventory') {
        const derived = dsiWizardActiveStepFromServer({
          stage: jobDetail.stage ?? '',
          status: jobDetail.status ?? '',
          import_mode: jobDetail.import_mode ?? '',
        });
        if (derived != null) setActiveStep(derived);
      } else if (jobDetail.template_slug === 'inbound_shipments') {
        const derived = shipmentWizardActiveStepFromServer({
          stage: jobDetail.stage ?? '',
          status: jobDetail.status ?? '',
        });
        if (derived != null) setActiveStep(derived);
      } else {
        setActiveStep(4);
      }
    }
  }, [jobDetail, visibleTemplates, searchParams, jobIdParam]);

  useEffect(() => {
    if (jobIdParam == null || !jobDetailFetched) return;
    if (jobDetail) return;
    if (!jobDetailIsError) return;
    const msg =
      jobDetailErr instanceof Error ? jobDetailErr.message : String(jobDetailErr ?? '');
    if (
      /\b404\b/.test(msg) ||
      /not\s+found/i.test(msg) ||
      /job\s+not\s+found/i.test(msg)
    ) {
      router.replace('/admin/imports');
    }
  }, [jobIdParam, jobDetail, jobDetailFetched, jobDetailIsError, jobDetailErr, router]);

  // PM validation breakdown: authoritative per-code totals from the pm_validation_summary
  // row (which carries true counts even though stored detail rows are capped per code),
  // each with a sample message so the user can see WHAT failed (e.g. unknown_channel 'ROG Strix').
  const pmErrorBreakdown = useMemo<Array<{ code: string; count: number; sample: string | null; severity: string }>>(() => {
    if (!isPm || !previewRows?.length) return [];
    let counts: Record<string, number> | null = null;
    const summaryRow = previewRows.find((r) => r.code === 'pm_validation_summary');
    if (summaryRow?.message) {
      try {
        const parsed = JSON.parse(summaryRow.message) as { code_counts?: Record<string, number> };
        if (parsed && typeof parsed === 'object' && parsed.code_counts) counts = parsed.code_counts;
      } catch {
        counts = null;
      }
    }
    if (!counts) {
      counts = {};
      for (const r of previewRows) {
        if (r.code && r.code !== 'pm_validation_summary') counts[r.code] = (counts[r.code] ?? 0) + 1;
      }
    }
    const sample: Record<string, string> = {};
    const severityByCode: Record<string, string> = {};
    for (const r of previewRows) {
      if (!r.code || r.code === 'pm_validation_summary') continue;
      if (!sample[r.code] && r.message) sample[r.code] = r.message;
      if (!severityByCode[r.code]) severityByCode[r.code] = r.severity;
    }
    return Object.entries(counts)
      .filter(([code]) => code && code !== 'pm_validation_summary')
      .sort((a, b) => b[1] - a[1])
      .map(([code, count]) => ({
        code,
        count,
        sample: sample[code] ?? null,
        severity: severityByCode[code] ?? 'info',
      }));
  }, [isPm, previewRows]);

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


  type DsiMappingState = {
    id: number;
    stage: string;
    status: string;
    import_mode?: string | null;
    template_slug?: string | null;
    error_summary?: string | null;
    file_headers: string[];
    field_mapping: Record<string, string> | Record<string, Record<string, string>>;
    multi_sheet?: boolean;
    multi_file?: boolean;
    dsi_workbook?: {
      multi_sheet?: boolean;
      sheet_count?: number;
      sheets?: Array<{
        sheet_name?: string | null;
        sheet_key?: string;
        mapping_key?: string;
        source_file?: string;
        row_count?: number;
        columns?: string[];
        column_samples?: Record<string, string[]>;
        dsi_mappable?: boolean;
      }>;
      skipped_sheets?: Array<{ sheet_name?: string; reason?: string }>;
    } | null;
    sheet_field_mappings?: Record<
      string,
      {
        field_mapping: Record<string, string>;
        blocking_mapping_errors: Array<{ code: string; message: string }>;
        mapping_valid: boolean;
        mapping_adjustment_notices?: Array<{ code: string; message: string }>;
        column_samples?: Record<string, string[]>;
        column_mapping_hints?: Record<string, unknown>;
      }
    >;
    canonical_targets: string[];
    blocking_mapping_errors: Array<{ code: string; message: string }>;
    mapping_valid: boolean;
    column_samples?: Record<string, string[]>;
    mapping_adjustment_notices?: Array<{ code: string; message: string }>;
    column_mapping_hints?: Record<
      string,
      {
        suggested_target?: string | null;
        confidence?: number;
        reasons?: string[];
        reason_summary?: string;
        runner_up?: string | null;
        sample_values?: string[];
      }
    >;
    field_target_descriptions?: Record<string, string>;
  };

  const { data: dsiMappingState, refetch: refetchDsiMapping } = useQuery({
    queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId!),
    queryFn: ({ signal }) =>
      apiGet<DsiMappingState>(`/api/v1/imports/jobs/${lastJobId}/dsi-mapping-state`, { signal }),
    enabled: Boolean(isDsi && lastJobId != null && activeStep >= 5),
  });

  const dsiIsMultiSheet = Boolean(
    dsiMappingState?.multi_sheet || isNestedDsiFieldMapping(dsiMappingState?.field_mapping)
  );

  const dsiSheetKeys = useMemo(() => {
    if (!dsiIsMultiSheet || !dsiMappingState) return [] as string[];
    const fromWb = (dsiMappingState.dsi_workbook?.sheets ?? [])
      .map((s) => s.mapping_key || s.sheet_key)
      .filter((k): k is string => Boolean(k));
    if (fromWb.length) return fromWb;
    if (isNestedDsiFieldMapping(dsiMappingState.field_mapping)) {
      return Object.keys(dsiMappingState.field_mapping);
    }
    return Object.keys(dsiMappingState.sheet_field_mappings ?? {});
  }, [dsiIsMultiSheet, dsiMappingState]);

  const dsiServerMappingGateOk = useMemo(() => {
    const fm = dsiMappingState?.field_mapping;
    if (isNestedDsiFieldMapping(fm)) return dsiGateFromNestedMapping(fm);
    return dsiGateFromMapping((fm as Record<string, string>) ?? {});
  }, [dsiMappingState?.field_mapping]);

  const dsiCanonSet = useMemo(
    () => new Set(dsiMappingState?.canonical_targets ?? []),
    [dsiMappingState?.canonical_targets]
  );

  const dsiMappingTargetOptions = useMemo<CanonicalTargetOption[]>(
    () =>
      (dsiMappingState?.canonical_targets ?? []).map((t) => ({
        value: t,
        label: dsiTargetLabel(t),
        description: dsiTargetDescription(t) ?? dsiMappingState?.field_target_descriptions?.[t],
      })),
    [dsiMappingState?.canonical_targets, dsiMappingState?.field_target_descriptions]
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
    setDsiNestedMapDraft({});
    setDsiActiveSheetKey(null);
    setDsiContinueGateKey(null);
  }, [isDsi, lastJobId]);

  useEffect(() => {
    if (!dsiIsMultiSheet || !dsiSheetKeys.length) return;
    if (dsiActiveSheetKey && dsiSheetKeys.includes(dsiActiveSheetKey)) return;
    setDsiActiveSheetKey(dsiSheetKeys[0] ?? null);
  }, [dsiIsMultiSheet, dsiSheetKeys, dsiActiveSheetKey]);

  const dsiMappingDraftDirty = useMemo(() => {
    if (!isDsi || !dsiMappingState) return false;
    if (dsiIsMultiSheet && isNestedDsiFieldMapping(dsiMappingState.field_mapping)) {
      const server = dsiMappingState.field_mapping;
      for (const key of dsiSheetKeys) {
        const sMap = server[key] ?? {};
        const dMap = dsiNestedMapDraft[key] ?? {};
        const headers = new Set([...Object.keys(sMap), ...Object.keys(dMap)]);
        for (const h of headers) {
          if ((dMap[h] ?? '') !== (sMap[h] ?? '')) return true;
        }
      }
      return false;
    }
    if (!dsiMappingState.file_headers?.length) return false;
    const server = (dsiMappingState.field_mapping as Record<string, string>) ?? {};
    for (const h of dsiMappingState.file_headers) {
      if ((dsiMapDraft[h] ?? '') !== (server[h] ?? '')) return true;
    }
    for (const k of Object.keys(dsiMapDraft)) {
      if (!dsiMappingState.file_headers.includes(k) && dsiMapDraft[k]) return true;
    }
    return false;
  }, [
    isDsi,
    dsiIsMultiSheet,
    dsiMapDraft,
    dsiNestedMapDraft,
    dsiSheetKeys,
    dsiMappingState,
  ]);

  useEffect(() => {
    if (!isDsi || activeStep < 5 || !dsiMappingState) return;
    if (dsiIsMultiSheet && isNestedDsiFieldMapping(dsiMappingState.field_mapping)) {
      const next: Record<string, Record<string, string>> = {};
      for (const key of dsiSheetKeys) {
        const serverSheet =
          dsiMappingState.sheet_field_mappings?.[key]?.field_mapping ??
          dsiMappingState.field_mapping[key] ??
          {};
        const sheetNext: Record<string, string> = {};
        for (const [h, v] of Object.entries(serverSheet)) {
          if (v && dsiCanonSet.has(v)) sheetNext[h] = v;
        }
        next[key] = sheetNext;
      }
      setDsiNestedMapDraft(next);
      return;
    }
    if (!dsiMappingState.file_headers?.length) return;
    const server = (dsiMappingState.field_mapping as Record<string, string>) ?? {};
    const next: Record<string, string> = {};
    for (const h of dsiMappingState.file_headers) {
      const v = server[h];
      if (v && dsiCanonSet.has(v)) next[h] = v;
    }
    setDsiMapDraft(next);
  }, [
    isDsi,
    activeStep,
    dsiIsMultiSheet,
    dsiMappingState?.id,
    dsiServerMappingKey,
    dsiMappingState?.file_headers,
    dsiSheetKeys,
    dsiCanonSet,
    dsiMappingState,
  ]);

  const saveDsiMapping = useMutation({
    mutationFn: async () => {
      if (lastJobId == null) throw new Error('No job');
      const payload = dsiIsMultiSheet ? dsiNestedMapDraft : dsiMapDraft;
      const res = await fetch(apiUrl(`/api/v1/imports/jobs/${lastJobId}/dsi-field-mapping`), {
        method: 'PUT',
        headers: { ...defaultHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ field_mapping: payload }),
      });
      if (!res.ok) throw new Error(await readFetchError(res));
      return res.json() as Promise<DsiMappingState>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
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
      const json = (await res.json()) as DsiMappingState & { async?: boolean; task_id?: string | null };
      return { async: Boolean(json.async), taskId: json.task_id ?? null };
    },
    onSuccess: async (data) => {
      if (data.async) {
        const jid = lastJobIdRef.current;
        if (jid != null) {
          notifyDsiAsyncPipelineStarted(qc, jid, {
            taskId: data.taskId,
            onSetAsync: setDsiValidateAsync,
          });
        } else {
          setDsiValidateAsync(true);
        }
      } else {
        setDsiValidateAsync(false);
      }
      const jid = lastJobIdRef.current;
      void qc.invalidateQueries({ queryKey: ['import-job', jid] });
      void qc.invalidateQueries({ queryKey: ['dsi-async-validate-import-job', jid] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', jid] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(jid) });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(jid) });
      await refetchPreview();
      await refetchDsiMapping();
    },
    onError: () => {
      setDsiContinueGateKey(null);
      setDsiValidateAsync(false);
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });

  const { data: dsiValidatePollJob } = useQuery({
    // Dedicated key so this poller is not merged with `['import-job', jobIdParam]` (revisit flow),
    // which would drop `refetchInterval` and stop polling while stage is still `dsi_mapping_ready`.
    queryKey: ['dsi-async-validate-import-job', lastJobId],
    queryFn: ({ signal }) => apiGet<Job>(`/api/v1/imports/jobs/${lastJobId!}`, { signal }),
    enabled: Boolean(isDsi && lastJobId != null && dsiValidateAsync),
    refetchInterval: (q) => {
      const j = q.state.data;
      if (!j) return 1500;
      const status = (j.status || '').trim().toLowerCase();
      if (status === 'running') return 1500;
      const st = (j.stage || '').trim();
      if (st === 'validated' || st === 'failed') return false;
      return 1500;
    },
  });

  // Apply poll: terminal on `loaded`/`failed` (apply's terminal stage), NOT `validated` — apply
  // passes through `validated` before the worker's complete step upserts facts and promotes to `loaded`.
  const { data: dsiApplyPollJob } = useQuery({
    queryKey: ['dsi-async-apply-import-job', lastJobId],
    queryFn: ({ signal }) => apiGet<Job>(`/api/v1/imports/jobs/${lastJobId!}`, { signal }),
    enabled: Boolean(isDsi && lastJobId != null && dsiApplyAsync),
    refetchInterval: (q) => {
      const j = q.state.data;
      if (!j) return 1500;
      const st = (j.stage || '').trim();
      if (st === 'loaded' || st === 'failed') return false;
      return 1500;
    },
  });

  const { data: dsiProgress } = useImportJobProgressQuery(lastJobId ?? undefined, {
    enabled: Boolean(isDsi && lastJobId != null && (dsiValidateAsync || dsiApplyAsync)),
  });

  useEffect(() => {
    if (!dsiValidateAsync) return;
    const j = dsiValidatePollJob;
    if (!j) return;
    const status = (j.status || '').trim().toLowerCase();
    if (status === 'running') return;
    const st = (j.stage || '').trim();
    const progressPhase = String(dsiProgress?.phase ?? '').trim();
    if (progressPhase === 'failed' || st === 'failed') {
      setDsiValidateAsync(false);
      return;
    }
    if (
      progressPhase === 'complete' ||
      st === 'validated' ||
      status === 'completed' ||
      status === 'completed_with_errors'
    ) {
      setDsiValidateAsync(false);
      void (async () => {
        await refetchDsiImportJobStewardQueries(qc, j.id, { includeImportJobsList: true });
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        await refetchDsiMapping();
        await refetchPreview();
      })();
    }
  }, [dsiValidateAsync, dsiValidatePollJob, dsiProgress?.phase, qc, refetchDsiMapping, refetchPreview]);

  useEffect(() => {
    if (!dsiApplyAsync) return;
    const j = dsiApplyPollJob;
    if (!j) return;
    const status = (j.status || '').trim().toLowerCase();
    const st = (j.stage || '').trim();
    if (status === 'running' && st !== 'loaded' && st !== 'failed') return;
    // Terminal for apply is ``loaded`` or ``failed`` only. Step 1 of apply leaves the job at
    // ``validated`` + ``completed`` — that is NOT apply-complete; Step 2 still has to upsert facts.
    if (st === 'loaded' || st === 'failed') {
      setDsiApplyAsync(false);
      void (async () => {
        await refetchDsiImportJobStewardQueries(qc, j.id, { includeImportJobsList: true });
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        await refetchDsiMapping();
        await refetchPreview();
      })();
    }
  }, [dsiApplyAsync, dsiApplyPollJob, qc, refetchDsiMapping, refetchPreview]);

  const handleDsiAsyncPipelineStarted = useCallback(
    (args: { importJobId: number; taskId?: string | null }) => {
      if (args.importJobId !== lastJobId) return;
      notifyDsiAsyncPipelineStarted(qc, args.importJobId, {
        taskId: args.taskId,
        onSetAsync: setDsiValidateAsync,
      });
    },
    [lastJobId, qc]
  );

  const dsiPipelineInFlight = useMemo(() => {
    if (dsiValidateAsync || dsiApplyAsync) return true;
    const j = dsiValidatePollJob ?? dsiApplyPollJob;
    if (!j) return false;
    return (j.status || '').trim().toLowerCase() === 'running';
  }, [dsiValidateAsync, dsiApplyAsync, dsiValidatePollJob, dsiApplyPollJob]);

  useEffect(() => {
    dsiValidate.reset();
    setDsiValidateAsync(false);
    setDsiApplyAsync(false);
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
      // Apply now dispatches to the worker and returns immediately with {async:true,...}; the
      // dedicated apply poll drives the lifecycle to `loaded`. (Sync fallback returns DsiMappingState.)
      return res.json() as Promise<DsiMappingState & { async?: boolean; task_id?: string | null }>;
    },
    onSuccess: (data) => {
      if (data && (data as { async?: boolean }).async) {
        setDsiApplyAsync(true);
      }
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
    onError: () => {
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });

  const dsiApplyComplete = useMutation({
    // Finalize to loaded must NOT run synchronously in the request path — the full re-resolve +
    // fact upsert for large jobs exceeds the proxy headers timeout (~300s) and returns a spurious
    // 500 even though the worker committed facts. Dispatch through the same async worker as Apply
    // (run_dsi_apply_sync → complete_dsi_import_job_to_loaded) and let the apply poll drive to loaded.
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
      return res.json() as Promise<DsiMappingState & { async?: boolean; task_id?: string | null }>;
    },
    onSuccess: (data) => {
      if (data && (data as { async?: boolean }).async) {
        setDsiApplyAsync(true);
      }
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
    onError: () => {
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(lastJobId) });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });

  const dsiCanFinalizeToLoaded = useMemo(() => {
    if (!isDsi || lastJobId == null) return false;
    const st = (dsiMappingState?.stage ?? '').trim();
    const mode = (dsiMappingState?.import_mode ?? '').trim();
    return st === 'validated' && mode === 'apply';
  }, [isDsi, lastJobId, dsiMappingState?.stage, dsiMappingState?.import_mode]);

  const dsiCanContinueToApply = useMemo(
    () =>
      dsiContinueToApplyAllowed(dsiContinueGateKey, lastJobId, dsiMappingState?.field_mapping, distributorSiSummary, {
        isValidating: dsiValidate.isPending || dsiPipelineInFlight,
        hasServerGate: dsiServerMappingGateOk,
      }),
    [
      dsiContinueGateKey,
      lastJobId,
      dsiMappingState?.field_mapping,
      distributorSiSummary,
      dsiValidate.isPending,
      dsiPipelineInFlight,
      dsiServerMappingGateOk,
    ]
  );

  const dsiValidateStage = useMemo(() => {
    const polled = (dsiValidatePollJob?.stage || '').trim();
    if (polled) return polled;
    return (dsiMappingState?.stage || '').trim();
  }, [dsiValidatePollJob?.stage, dsiMappingState?.stage]);

  const dsiJobSnapshotForRouting = useMemo(() => {
    const job =
      (dsiValidatePollJob?.id === lastJobId ? dsiValidatePollJob : null) ??
      (dsiApplyPollJob?.id === lastJobId ? dsiApplyPollJob : null) ??
      (jobDetail?.id === lastJobId && jobDetail.template_slug === 'distributor_inventory'
        ? jobDetail
        : null) ??
      (dsiMappingState?.id === lastJobId ? dsiMappingState : null);
    if (!job) {
      return { stage: dsiValidateStage, status: '' };
    }
    return {
      stage: String(job.stage ?? dsiValidateStage ?? ''),
      status: String(job.status ?? ''),
    };
  }, [
    dsiValidatePollJob,
    dsiApplyPollJob,
    jobDetail,
    dsiMappingState,
    lastJobId,
    dsiValidateStage,
  ]);

  const dsiValidationComplete = useMemo(
    () => dsiJobHasValidationComplete(dsiJobSnapshotForRouting),
    [dsiJobSnapshotForRouting]
  );

  const dsiDerivedStepRef = useRef<{ jobId: number | null; step: number | null }>({ jobId: null, step: null });
  const shipmentDerivedStepRef = useRef<{ jobId: number | null; step: number | null }>({ jobId: null, step: null });

  // Leaving a ?job= deep link (sidebar Import Center → bare /admin/imports) must reset wizard state.
  useEffect(() => {
    if (searchParams.get('template')) return;
    if (jobIdParam != null) return;
    if (!isJobRevisitMode) return;

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
    setShipmentMapDraft({});
    setShipmentValidateAsync(false);
    setDsiValidateAsync(false);
    setDsiApplyAsync(false);
    setUploadZoneExpanded(false);
    shipmentDerivedStepRef.current = { jobId: null, step: null };
    dsiDerivedStepRef.current = { jobId: null, step: null };
  }, [jobIdParam, isJobRevisitMode, searchParams]);

  useEffect(() => {
    if (!isDsi || lastJobId == null) return;
    const job =
      (dsiValidatePollJob?.id === lastJobId ? dsiValidatePollJob : null) ??
      (dsiApplyPollJob?.id === lastJobId ? dsiApplyPollJob : null) ??
      (jobDetail?.id === lastJobId && jobDetail.template_slug === 'distributor_inventory'
        ? jobDetail
        : null) ??
      (dsiMappingState?.id === lastJobId ? dsiMappingState : null);
    if (!job) return;
    if (activeStep < 4 && jobIdParam !== lastJobId) return;

    const derived = dsiWizardActiveStepFromServer({
      stage: String(job.stage ?? ''),
      status: String(job.status ?? ''),
      import_mode: String((job as { import_mode?: string | null }).import_mode ?? ''),
    });
    if (derived == null) return;

    if ((dsiPipelineInFlight || dsiValidateAsync) && activeStep >= 6 && derived < 6) return;
    // Apply in flight or on apply step — do not yank back to steward while finalize runs.
    if (dsiApplyAsync && activeStep >= 7 && derived === 6) return;

    if (dsiDerivedStepRef.current.jobId !== lastJobId) {
      dsiDerivedStepRef.current = { jobId: lastJobId, step: null };
    }
    if (dsiDerivedStepRef.current.step === derived) return;
    dsiDerivedStepRef.current = { jobId: lastJobId, step: derived };
    setActiveStep((prev) => (prev === derived ? prev : derived));
  }, [
    isDsi,
    lastJobId,
    jobIdParam,
    activeStep,
    dsiValidatePollJob,
    dsiApplyPollJob,
    jobDetail,
    dsiMappingState,
    dsiPipelineInFlight,
    dsiValidateAsync,
    dsiApplyAsync,
  ]);

  const { data: dsiJobIntelligence } = useQuery({
    queryKey: ['dsi-job-intelligence', lastJobId],
    queryFn: ({ signal }) => apiGet<Job>(`/api/v1/imports/jobs/${lastJobId!}`, { signal }),
    enabled: Boolean(isDsi && lastJobId != null && dsiValidationComplete),
  });

  const dsiIntelligenceState = useMemo((): DsiIntelligenceState | null => {
    const meta =
      dsiValidatePollJob?.staged_metadata ??
      dsiJobIntelligence?.staged_metadata ??
      null;
    if (!meta || typeof meta !== 'object') return null;
    const intel = (meta as Record<string, unknown>).intelligence_state;
    return intel && typeof intel === 'object' ? (intel as DsiIntelligenceState) : null;
  }, [dsiValidatePollJob?.staged_metadata, dsiJobIntelligence?.staged_metadata]);

  const dsiHasValidateResult = dsiValidationComplete || Boolean(distributorSiSummary);

  // Unlock “Continue to apply” whenever the latest server summary clears blockers — not only
  // when the main Validate button’s mutation onSuccess runs (server revalidate + async poll
  // also refresh preview rows but previously left dsiContinueGateKey null).
  useEffect(() => {
    if (!isDsi) return;
    if (dsiMappingDraftDirty) {
      setDsiContinueGateKey(null);
      return;
    }
    if (dsiPipelineInFlight || dsiValidate.isPending) {
      setDsiContinueGateKey(null);
      return;
    }
    if (!dsiValidationComplete || !dsiServerMappingGateOk) return;
    setDsiContinueGateKey(
      computeDsiContinueGateKey(lastJobId, dsiMappingState?.field_mapping, distributorSiSummary)
    );
  }, [
    isDsi,
    lastJobId,
    distributorSiSummary,
    dsiValidationComplete,
    dsiPipelineInFlight,
    dsiValidate.isPending,
    dsiMappingDraftDirty,
    dsiServerMappingGateOk,
    dsiMappingState?.field_mapping,
  ]);

  useEffect(() => {
    if (!isDsi || !dsiMappingDraftDirty) return;
    setDsiContinueGateKey(null);
    setDsiValidateAsync(false);
    dsiValidate.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when draft diverges from saved server mapping
  }, [isDsi, dsiMappingDraftDirty]);

  const dsiGateOk = useMemo(() => {
    if (dsiIsMultiSheet) return dsiGateFromNestedMapping(dsiNestedMapDraft);
    return dsiGateFromMapping(dsiMapDraft);
  }, [dsiIsMultiSheet, dsiMapDraft, dsiNestedMapDraft]);

  const dsiJobDisplay = useMemo(
    () =>
      deriveDsiJobDisplayState({
        status: dsiMappingState?.status,
        stage: dsiMappingState?.stage,
        errorSummary: dsiMappingState?.error_summary,
        progressPhase: dsiProgress?.phase,
        taskState: dsiProgress?.task_state,
        progressAt: dsiProgress?.progress_at,
        pipelineStartedAt: dsiProgress?.pipeline_started_at,
      }),
    [
      dsiMappingState?.status,
      dsiMappingState?.stage,
      dsiMappingState?.error_summary,
      dsiProgress?.phase,
      dsiProgress?.task_state,
      dsiProgress?.progress_at,
      dsiProgress?.pipeline_started_at,
    ]
  );

  const handleDsiJobStateRecovery = useCallback(() => {
    void refetchDsiMapping();
    if (lastJobId != null) {
      void qc.invalidateQueries({ queryKey: ['import-job-pipeline-progress', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-async-validate-import-job', lastJobId] });
    }
  }, [lastJobId, qc, refetchDsiMapping]);

  const dsiJobFailedAlert = useMemo(() => {
    if (!isDsi) return null;
    if (dsiJobDisplay.kind === 'failed') {
      return (
        <Alert severity="error" data-testid="dsi-job-failed-banner">
          Import job failed: {dsiJobDisplay.message}
        </Alert>
      );
    }
    if (dsiJobDisplay.kind === 'interrupted') {
      return (
        <Alert severity="warning" data-testid="dsi-job-interrupted-banner">
          {dsiJobDisplay.message}
        </Alert>
      );
    }
    if (dsiJobDisplay.kind === 'running_stale') {
      return (
        <Alert
          severity="warning"
          data-testid="dsi-job-stale-banner"
          action={
            <Button color="inherit" size="small" onClick={handleDsiJobStateRecovery}>
              Check now
            </Button>
          }
        >
          {dsiJobDisplay.message}
        </Alert>
      );
    }
    return null;
  }, [dsiJobDisplay, handleDsiJobStateRecovery, isDsi]);

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
      if (selectedSlug === 'distributor_inventory') {
        fd.append('dsi_workflow_mode', dsiWorkflowMode);
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
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(data.id) });
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.dsiMappingStateQueryKey(data.id) });
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
      const sts = (j.status || '').trim();
      if (sts === 'running') return 1500;
      // Keep polling through async validate while still at mapping_ready — otherwise the job
      // record never refreshes after the worker commits and the progress panel spins forever.
      if (shipmentValidateAsync && st === 'shipment_mapping_ready') return 1500;
      if (sts === 'completed' || sts === 'completed_with_errors') return 1500;
      if (st === 'validated' || st === 'loaded' || st === 'failed') return false;
      if (st === 'shipment_mapping_ready') return false;
      return 1500;
    },
  });

  useEffect(() => {
    if (!isShipmentEvidence || !shipmentImportJob) return;
    const st = (shipmentImportJob.stage || '').trim();
    const sts = (shipmentImportJob.status || '').trim();
    if (
      st === 'validated' ||
      st === 'loaded' ||
      st === 'failed' ||
      sts === 'completed' ||
      sts === 'completed_with_errors' ||
      sts === 'failed'
    ) {
      setShipmentValidateAsync(false);
    }
  }, [isShipmentEvidence, shipmentImportJob?.stage, shipmentImportJob?.status]);

  /** Job id for shipment column mapping + validate (matches steward poll id). */
  const shipmentMappingJobId: number | null = shipmentEvidencePollJobId ?? lastJobId ?? null;
  const shipmentStageTrim = (shipmentImportJob?.stage || '').trim();
  const shipmentPostValidateRemap =
    Boolean(isJobRevisitMode) && ['validated', 'loaded'].includes(shipmentStageTrim);
  const shipmentMappingPanelEnabled =
    shipmentStageTrim === 'shipment_mapping_ready' || shipmentPostValidateRemap;

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
        shipmentMappingPanelEnabled
    ),
  });

  const shipmentCanonSet = useMemo(
    () => new Set(shipmentMappingState?.canonical_targets ?? []),
    [shipmentMappingState?.canonical_targets]
  );

  const shipmentMappingTargetOptions = useMemo<CanonicalTargetOption[]>(
    () =>
      (shipmentMappingState?.canonical_targets ?? []).map((t) => ({
        value: t,
        label: SHIPMENT_FIELD_LABELS[t] ?? t,
        description: shipmentMappingState?.field_target_descriptions?.[t],
      })),
    [shipmentMappingState?.canonical_targets, shipmentMappingState?.field_target_descriptions]
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
      const body = (await res.json()) as { async?: boolean };
      return { jid, async: Boolean(body?.async) };
    },
    onSuccess: (data) => {
      if (data.async) setShipmentValidateAsync(true);
      void qc.invalidateQueries({ queryKey: ['import-job', data.jid] });
      void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', data.jid] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', data.jid] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void refetchPreview();
    },
  });

  const shipmentStage = (shipmentImportJob?.stage || '').trim();
  const shipmentStatus = (shipmentImportJob?.status || '').trim();
  const shipmentJobSnapshot = useMemo(
    () => ({ stage: shipmentStage, status: shipmentStatus }),
    [shipmentStage, shipmentStatus]
  );
  const shipmentValidationComplete = shipmentJobHasValidationComplete(shipmentJobSnapshot);
  const shipmentServerPipelineInFlight = shipmentJobPipelineInFlight(shipmentJobSnapshot);
  const shipmentPipelineInFlight = Boolean(
    shipmentValidateRun.isPending || shipmentValidateAsync || shipmentServerPipelineInFlight
  );
  const shipmentValidatePollEnabled = Boolean(
    isShipmentEvidence && shipmentMappingJobId != null && shipmentPipelineInFlight
  );
  const { data: shipmentProgress } = useImportJobProgressQuery(shipmentMappingJobId ?? undefined, {
    enabled: shipmentValidatePollEnabled,
  });
  const shipmentProgressPhase = (shipmentProgress?.phase ?? '').trim();
  const shipmentValidating = shipmentPipelineInFlight && !shipmentValidationComplete;

  useEffect(() => {
    if (!isShipmentEvidence || lastJobId == null) return;
    const job =
      (shipmentImportJob?.id === lastJobId ? shipmentImportJob : null) ??
      (jobDetail?.id === lastJobId && jobDetail.template_slug === 'inbound_shipments' ? jobDetail : null);
    if (!job) return;
    if (activeStep < 3 && jobIdParam !== lastJobId) return;

    const derived = shipmentWizardActiveStepFromServer({
      stage: String(job.stage ?? ''),
      status: String(job.status ?? ''),
    });
    if (derived == null) return;

    if ((shipmentPipelineInFlight || shipmentValidateAsync) && activeStep >= 5 && derived < 5) return;

    if (shipmentDerivedStepRef.current.jobId !== lastJobId) {
      shipmentDerivedStepRef.current = { jobId: lastJobId, step: null };
    }
    if (shipmentDerivedStepRef.current.step === derived) return;
    shipmentDerivedStepRef.current = { jobId: lastJobId, step: derived };
    setActiveStep((prev) => (prev === derived ? prev : derived));
  }, [
    isShipmentEvidence,
    lastJobId,
    jobIdParam,
    activeStep,
    shipmentImportJob,
    jobDetail,
    shipmentPipelineInFlight,
    shipmentValidateAsync,
  ]);

  useEffect(() => {
    if (!isShipmentEvidence || shipmentMappingJobId == null) return;
    const phase = (shipmentProgress?.phase ?? '').trim();
    if (phase !== 'complete' && phase !== 'failed') return;
    setShipmentValidateAsync(false);
    void qc.invalidateQueries({ queryKey: ['import-job', shipmentMappingJobId] });
    void qc.invalidateQueries({ queryKey: ['import-jobs'] });
    void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', shipmentMappingJobId] });
    void qc.invalidateQueries({ queryKey: ['import-job-rows', shipmentMappingJobId] });
  }, [isShipmentEvidence, shipmentMappingJobId, shipmentProgress?.phase, qc]);

  const shipmentMappingDraftDirty = useMemo(() => {
    if (!shipmentMappingState?.file_headers?.length) return false;
    const server = shipmentMappingState.field_mapping ?? {};
    for (const h of shipmentMappingState.file_headers) {
      if ((shipmentMapDraft[h] ?? '') !== (server[h] ?? '')) return true;
    }
    return false;
  }, [shipmentMappingState, shipmentMapDraft]);

  const shipmentGateOk = Boolean(
    shipmentMappingState?.mapping_valid && !shipmentMappingDraftDirty && shipmentMappingState?.file_headers?.length
  );

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
      const text = await res.text();
      if (res.status !== 202 && !res.ok) {
        throw new Error(
          await readFetchError(new Response(text, { status: res.status, statusText: res.statusText }))
        );
      }
      return (text ? JSON.parse(text) : {}) as {
        validation_passed?: boolean | null;
        status?: string;
        pm_validate?: { outcome?: string; message?: string };
      };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pm-import-state', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
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

  const {
    data: pmJobState,
    refetch: refetchPmState,
    isError: pmStateIsError,
    isLoading: pmStateLoading,
    error: pmStateErr,
  } = useQuery({
    queryKey: ['pm-import-state', lastJobId],
    queryFn: ({ signal }) => apiGet<PmJobState>(`/api/v1/imports/product-master/jobs/${lastJobId}/state`, { signal }),
    enabled: Boolean(isPm && lastJobId != null),
    refetchInterval: (query) => {
      const externalBusy =
        savePmMapping.isPending || validatePm.isPending || commitPm.isPending;
      const data = query.state.data as PmJobState | undefined;
      const commitBusy =
        data?.status === 'commit_queued' || data?.status === 'commit_running';
      const validateBusy =
        data?.status === 'validate_queued' || data?.status === 'validate_running';
      return externalBusy || commitBusy || validateBusy ? 2000 : false;
    },
  });

  const pmStateLoadMessage = useMemo(() => {
    if (!pmStateIsError) return null;
    const raw = safeDisplayError(pmStateErr);
    if (/database temporarily unavailable/i.test(raw) || /\b503\b/.test(raw)) {
      return 'Database temporarily unavailable — please retry.';
    }
    if (/\b404\b/.test(raw) || /not\s+found/i.test(raw)) {
      return 'Product Master import job not found. It may have been deleted.';
    }
    return raw || 'Unable to load Product Master job state — please retry.';
  }, [pmStateIsError, pmStateErr]);

  const hdrKey = pmJobState?.file_headers?.join('|') ?? '';
  useEffect(() => {
    if (!isPm || activeStep !== 4 || !pmJobState?.file_headers?.length) return;
    setPmColumns(
      initPmColumnDrafts(pmJobState.file_headers, pmJobState.suggested_mapping, pmJobState.mapping_decisions)
    );
  }, [isPm, activeStep, lastJobId, hdrKey, pmJobState?.suggested_mapping, pmJobState?.mapping_decisions]);

  // Align wizard body with polled PM job state (upload, mapping save, validate/commit progress).
  // Only react when the *server-derived* step actually changes for this job — never on plain
  // activeStep changes — so manual Back navigation (e.g. from a validation_failed Validate step
  // back to Column mapping) is not immediately yanked forward again by the next poll.
  const pmDerivedStepRef = useRef<{ jobId: number | null; step: number | null }>({ jobId: null, step: null });
  useEffect(() => {
    if (!isPm || lastJobId == null || !pmJobState || pmJobState.id !== lastJobId) return;
    if (activeStep < 3 && jobIdParam !== lastJobId) return;
    const derived = pmWizardActiveStepFromServer(pmJobState);
    if (derived == null) return;
    if (pmDerivedStepRef.current.jobId !== lastJobId) {
      pmDerivedStepRef.current = { jobId: lastJobId, step: null };
    }
    if (pmDerivedStepRef.current.step === derived) return;
    pmDerivedStepRef.current = { jobId: lastJobId, step: derived };
    setActiveStep((prev) => (prev === derived ? prev : derived));
  }, [
    isPm,
    lastJobId,
    jobIdParam,
    activeStep,
    pmJobState,
  ]);

  // PM async validation finishes in a background worker; only pm-import-state is polled.
  // Refetch the row-result detail (used by the per-code breakdown + detail table) when the
  // job transitions out of validate_queued/validate_running into a terminal validate state,
  // otherwise the Validate step shows only the bare error count and no per-row detail.
  const pmPrevStatusRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isPm || lastJobId == null || !pmJobState || pmJobState.id !== lastJobId) return;
    const prev = pmPrevStatusRef.current;
    const cur = pmJobState.status ?? null;
    pmPrevStatusRef.current = cur;
    const wasValidating = prev === 'validate_running' || prev === 'validate_queued';
    const nowDone = cur === 'validated' || cur === 'validation_failed';
    if (wasValidating && nowDone) {
      void qc.invalidateQueries({ queryKey: ['import-job-rows', lastJobId] });
      void refetchPreview();
    }
  }, [isPm, lastJobId, pmJobState, qc, refetchPreview]);

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

  const boundImportJobId = lastJobId ?? (isJobRevisitMode && jobIdParam != null ? jobIdParam : null);

  const boundImportJobMeta = useMemo(() => {
    if (boundImportJobId == null) return null;
    if (jobDetail?.id === boundImportJobId) {
      return {
        id: boundImportJobId,
        file_name: jobDetail.file_name,
        stage: jobDetail.stage,
      };
    }
    if (shipmentImportJob && shipmentEvidencePollJobId === boundImportJobId) {
      return {
        id: boundImportJobId,
        file_name: shipmentImportJob.file_name,
        stage: shipmentImportJob.stage,
      };
    }
    return { id: boundImportJobId, file_name: null as string | null, stage: null as string | null };
  }, [boundImportJobId, jobDetail, shipmentImportJob, shipmentEvidencePollJobId]);

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
      <UnifiedLineupImportDialog
        open={unifiedLineupOpen}
        onClose={() => setUnifiedLineupOpen(false)}
        initialPeriodLabel={unifiedPeriodPrefill}
      />
      <DsiBulkUploadDialog
        open={dsiBulkUploadOpen}
        onClose={() => setDsiBulkUploadOpen(false)}
        sourceId={typeof sourceId === 'number' ? sourceId : null}
        dsiWorkflowMode={dsiWorkflowMode}
        onWorkflowModeChange={setDsiWorkflowMode}
        onJobsCreated={(ids) => {
          if (ids[0] != null) {
            setLastJobId(ids[0]);
            setActiveStep(5);
          }
          void qc.invalidateQueries({ queryKey: ['import-jobs'] });
        }}
      />
      <BulkLineupBackfillDialog
        open={bulkLineupBackfillOpen}
        onClose={() => setBulkLineupBackfillOpen(false)}
      />
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
              <Card
                variant="outlined"
                sx={{ width: 280, borderColor: 'primary.main' }}
                data-testid="unified-lineup-import-card"
              >
                <CardActionArea onClick={() => setUnifiedLineupOpen(true)}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={600}>
                      Lineup (unified import)
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                      unified_lineup · multi-file
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Upload several lineup files at once. Each file becomes its own case, parsed
                      async with the full backwards pricing chain and period inference.
                    </Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                      <Chip size="small" label="Multi-file" color="primary" variant="outlined" />
                      <Chip size="small" label="Async per file" variant="outlined" />
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
              <Card
                variant="outlined"
                sx={{ width: 280, borderColor: 'secondary.main' }}
                data-testid="bulk-lineup-backfill-card"
              >
                <CardActionArea onClick={() => setBulkLineupBackfillOpen(true)}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={600}>
                      Bulk historical lineup backfill
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                      bulk_lineup_backfill · steward preview
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Multi-file archive upload with file-grain period/BU detection, sheet fan-out,
                      supersession preview, and batch apply. Flagged files never block good ones.
                    </Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                      <Chip size="small" label="Preview-first" color="secondary" variant="outlined" />
                      <Chip size="small" label="Supersession" variant="outlined" />
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
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
                      setLastJobId(null);
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
            <ImportFileUploadZone
              expanded
              onExpandedChange={() => {}}
              canUpload={!!canGoUpload}
              pending={pmUpload.isPending}
              error={pmUpload.isError ? safeDisplayError(pmUpload.error) : null}
              onFile={onFile}
              subtitle="Or choose a file. No catalog writes until you pass validation and commit on the last step."
              testIdPrefix="pm-upload"
            />
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
            {pmStateIsError ? (
              <Alert
                severity="error"
                action={
                  <Button color="inherit" size="small" onClick={() => void refetchPmState()}>
                    Retry
                  </Button>
                }
              >
                {pmStateLoadMessage}
              </Alert>
            ) : null}
            {pmStateLoading && !pmJobState?.file_headers?.length && !pmStateIsError ? (
              <Stack spacing={1}>
                <LinearProgress />
                <Typography variant="body2" color="text.secondary">
                  Loading Product Master job state…
                </Typography>
              </Stack>
            ) : null}
            {!pmStateIsError && !pmStateLoading && !pmJobState?.file_headers?.length ? (
              <Alert
                severity="warning"
                action={
                  <Button color="inherit" size="small" onClick={() => void refetchPmState()}>
                    Retry
                  </Button>
                }
              >
                Column mapping is not available — no file headers were returned for this job. Go back to
                upload or retry loading job state.
              </Alert>
            ) : null}
            {!pmStateIsError && pmJobState?.file_headers?.length ? (
              <>
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
                            prev.map((p) => (p.header === row.header ? { ...p, target: v } : p))
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
                      {row.target.trim() ? (
                        <TextField
                          label="Disposition"
                          size="small"
                          fullWidth
                          disabled
                          value="Mapped"
                          helperText="Column is mapped to a canonical system field"
                        />
                      ) : (
                        <FormControl size="small" fullWidth>
                          <InputLabel id={`disp-${row.header}`}>Disposition</InputLabel>
                          <Select
                            labelId={`disp-${row.header}`}
                            label="Disposition"
                            value={row.disposition}
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
                      )}
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
              </>
            ) : null}
            {pmStateIsError || (!pmJobState?.file_headers?.length && !pmStateLoading) ? (
              <Stack direction="row" spacing={1}>
                <Button onClick={() => setActiveStep(3)}>Back</Button>
                {pmStateIsError ? (
                  <Button variant="outlined" onClick={() => void refetchPmState()}>
                    Retry
                  </Button>
                ) : null}
              </Stack>
            ) : null}
          </Stack>
        ) : null}

        {activeStep === 5 && isPm ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Validate import (no catalog writes)</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="contained"
                onClick={() => void validatePm.mutateAsync()}
                disabled={
                  validatePm.isPending ||
                  pmJobState?.status === 'validate_queued' ||
                  pmJobState?.status === 'validate_running'
                }
              >
                Run validation
              </Button>
              {pmJobState?.validation_passed === true ? <Chip color="success" label="Passed" /> : null}
              {pmJobState?.validation_passed === false ? <Chip color="error" label="Failed" /> : null}
              {pmJobState?.validation_passed == null &&
              pmJobState?.status !== 'validate_queued' &&
              pmJobState?.status !== 'validate_running' ? (
                <Chip variant="outlined" label="Not run yet" />
              ) : null}
              {pmJobState?.status === 'validate_queued' || pmJobState?.status === 'validate_running' ? (
                <Chip color="info" label="Validating in background…" />
              ) : null}
            </Stack>
            {pmJobState?.status === 'validate_queued' || pmJobState?.status === 'validate_running' ? (
              <Alert severity="info">
                Validation is running in the background worker. This page will refresh automatically — you can leave and
                return later.
              </Alert>
            ) : null}
            {pmJobState?.error_summary ? <Alert severity="warning">{pmJobState.error_summary}</Alert> : null}
            {validatePm.isError ? (
              <Alert severity="error">{safeDisplayError(validatePm.error)}</Alert>
            ) : null}
            {pmErrorBreakdown.length > 0 ? (
              <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
                <Typography variant="subtitle2" gutterBottom>
                  What failed (grouped by issue)
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Issue</TableCell>
                      <TableCell align="right">Rows</TableCell>
                      <TableCell>Example</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {pmErrorBreakdown.map((b) => (
                      <TableRow key={b.code}>
                        <TableCell>
                          <Chip
                            size="small"
                            label={b.code}
                            color={b.severity === 'error' ? 'error' : b.severity === 'warning' ? 'warning' : 'default'}
                            variant={b.severity === 'info' ? 'outlined' : 'filled'}
                          />
                        </TableCell>
                        <TableCell align="right">{b.count.toLocaleString()}</TableCell>
                        <TableCell sx={{ maxWidth: 520, whiteSpace: 'normal' }}>{b.sample ?? '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Typography variant="caption" color="text.secondary">
                  Detail rows below are capped per issue; counts above are the true totals. Fix the mapping or source,
                  then re-run validation.
                </Typography>
              </Box>
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
            {(pmJobState?.staged_row_count ?? 0) > 0 ? (
              <Alert severity="info">
                Staged metadata rows: <strong>{pmJobState.staged_row_count}</strong> row(s) with stage_raw values —
                merged into <code>specs_json.import_staging</code> on commit (derived from the file, not stored on the job).
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
                  'Commit failed. Review import row messages below, fix the source or mapping, then try Commit again.'}
              </Alert>
            ) : null}
            {pmJobState?.status === 'commit_failed' && previewRows && previewRows.length > 0 ? (
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

        {activeStep === 3 && isShipmentEvidence && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="body2">
              Upload for <strong>{selectedTemplate.display_name}</strong> using provider{' '}
              <strong>{(sources ?? []).find((s) => s.id === sourceId)?.name ?? '—'}</strong>. Headers are detected
              automatically; map them in the next step.
            </Typography>
            {isJobRevisitMode && lastJobId != null && shipmentStageTrim === 'shipment_mapping_ready' ? (
              <Alert severity="info" data-testid="revisit-banner">
                Revisiting job <strong>#{lastJobId}</strong>. Adjust column mapping on the next step, then validate.
              </Alert>
            ) : isJobRevisitMode && lastJobId != null && shipmentPostValidateRemap ? (
              <Alert severity="info" data-testid="revisit-banner-post-validate-remap">
                Revisiting job <strong>#{lastJobId}</strong>. Use <strong>Column mapping</strong> to re-map, then{' '}
                <strong>Validate &amp; resolve</strong> to re-run validation without re-uploading.
              </Alert>
            ) : null}
            {!canGoUpload && !isJobRevisitMode ? (
              <Alert severity="warning">Complete provider and template details before uploading.</Alert>
            ) : null}
            <ImportFileUploadZone
              expanded
              onExpandedChange={() => {}}
              canUpload={!!canGoUpload}
              pending={upload.isPending}
              error={upload.isError ? safeDisplayError(upload.error) : null}
              onFile={onFile}
              subtitle="Or choose a file. Validation runs after column mapping."
              testIdPrefix="shipment-upload"
            />
            {upload.isSuccess && lastJobId != null ? (
              <Alert severity="success" data-testid="shipment-upload-success">
                Job <strong>#{lastJobId}</strong> created. Continue to column mapping.
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

        {activeStep === 4 && isShipmentEvidence && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">
              Column mapping {shipmentPostValidateRemap ? '(re-map & re-validate)' : '(required before validation)'}
            </Typography>
            {shipmentPostValidateRemap ? (
              <Alert severity="info">
                Re-validate replaces evidence lines for keys in the new parse and removes orphan lines whose keys no
                longer appear (steward mappings on surviving keys are preserved).
              </Alert>
            ) : (
              <Alert severity="info">
                Map each file column to a canonical shipment field, save, then continue to validation.
              </Alert>
            )}
            {shipmentMappingStateQueryError ? (
              <Alert severity="error">{safeDisplayError(shipmentMappingStateQueryErr)}</Alert>
            ) : null}
            {shipmentMappingStateLoading ? <LinearProgress /> : null}
            {!shipmentMappingPanelEnabled ? (
              <Alert severity="warning">Upload a file first — column headers appear after the job is created.</Alert>
            ) : null}
            {shipmentMappingPanelEnabled && shipmentMappingState?.blocking_mapping_errors?.length ? (
              <Alert severity="warning" data-testid="shipment-mapping-blocked">
                {shipmentMappingState.blocking_mapping_errors.map((e) => (
                  <Typography key={e.code} variant="body2" display="block">
                    {e.message}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {shipmentMappingPanelEnabled && shipmentMappingState?.file_headers?.length ? (
              <CanonicalColumnMappingPanel
                testIdPrefix="shipment"
                fileHeaders={shipmentMappingState.file_headers}
                draft={shipmentMapDraft}
                onChange={(next) => setShipmentMapDraft(next)}
                targetOptions={shipmentMappingTargetOptions}
                columnSamples={shipmentMappingState.column_samples}
                blockingErrors={shipmentMappingState.blocking_mapping_errors}
                adjustmentNotices={shipmentMappingState.mapping_adjustment_notices}
                requiredGroups={SHIPMENT_MAPPING_REQUIRED_GROUPS}
                formatSamples={formatDsiSamples}
                dirty={shipmentMappingDraftDirty}
              />
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button onClick={() => setActiveStep(3)}>Back</Button>
              <Button
                variant="outlined"
                disabled={saveShipmentMapping.isPending || !shipmentMappingState?.file_headers?.length}
                onClick={() => void saveShipmentMapping.mutateAsync()}
              >
                {saveShipmentMapping.isPending ? 'Saving…' : 'Save mapping'}
              </Button>
              <Button
                variant="contained"
                disabled={!shipmentGateOk || saveShipmentMapping.isPending}
                onClick={() =>
                  void saveShipmentMapping.mutateAsync().then(() => {
                    setActiveStep(5);
                  })
                }
              >
                Save &amp; continue to validate
              </Button>
            </Stack>
            {shipmentMappingDraftDirty ? (
              <Typography variant="caption" color="warning.main">
                Save mapping before continuing — draft has unsaved changes.
              </Typography>
            ) : null}
            {saveShipmentMapping.isError ? (
              <Alert severity="error">{safeDisplayError(saveShipmentMapping.error)}</Alert>
            ) : null}
          </Stack>
        ) : null}

        {activeStep === 5 && isShipmentEvidence && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Validate &amp; resolve entities</Typography>
            {!shipmentGateOk ? (
              <Alert severity="warning" data-testid="shipment-validate-blocked">
                Complete required column mappings on the previous step, then use <strong>Save mapping</strong> or{' '}
                <strong>Save &amp; continue to validate</strong> before running validation.
              </Alert>
            ) : null}
            {shipmentValidating ? (
              <Stack spacing={1}>
                <DsiValidateProgressPanel
                  progress={shipmentProgress}
                  isRunning={shipmentValidating}
                  title="Shipment validation"
                  phases={SHIPMENT_PROGRESS_PHASES}
                  phaseDescriptions={SHIPMENT_PROGRESS_DESCRIPTIONS}
                />
                <Typography variant="caption" color="text.secondary">
                  Validation runs in the background. Steward candidates refresh when the stage reaches{' '}
                  <strong>validated</strong>.
                </Typography>
              </Stack>
            ) : null}
            {shipmentValidateRun.isError ? (
              <Alert severity="error">{safeDisplayError(shipmentValidateRun.error)}</Alert>
            ) : null}
            {(shipmentEvidenceUrlUnlock || isShipmentEvidence) &&
            shipmentEvidencePollJobId != null &&
            shipmentEvidenceJobPollUnlocked &&
            shipmentImportJob &&
            shipmentValidationComplete ? (
              <>
                <Alert severity="success" data-testid="shipment-validate-finished">
                  Validation complete. Resolve distributor and channel partner tokens below, then continue to Apply.
                </Alert>
                <ShipmentEntityStewardPanel
                  importJobId={shipmentEvidencePollJobId}
                  shipmentPipelineRunning={shipmentValidating}
                  onInvalidate={() => {
                    if (shipmentMappingJobId == null) return;
                    void qc.invalidateQueries({ queryKey: ['import-job', shipmentMappingJobId] });
                    void qc.invalidateQueries({ queryKey: ['shipment-mapping-state', shipmentMappingJobId] });
                    void qc.invalidateQueries({ queryKey: ['import-job-rows', shipmentMappingJobId] });
                  }}
                  onAsyncPipelineStarted={() => setShipmentValidateAsync(true)}
                />
              </>
            ) : !shipmentValidationComplete && !shipmentValidating ? (
              <Alert severity="info">
                Run validation below after mapping is saved. Steward candidates appear when validation completes.
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              <Button onClick={() => setActiveStep(4)}>Back</Button>
              <Button
                variant="contained"
                disabled={
                  shipmentValidateRun.isPending ||
                  saveShipmentMapping.isPending ||
                  !shipmentGateOk ||
                  shipmentValidating
                }
                onClick={() => void shipmentValidateRun.mutateAsync()}
                data-testid="shipment-run-validation"
              >
                {shipmentValidateRun.isPending || shipmentValidateAsync || shipmentValidating
                  ? 'Validating…'
                  : shipmentValidationComplete
                    ? 'Re-run validation'
                    : 'Run validation'}
              </Button>
              {shipmentValidationComplete && !shipmentValidating ? (
                <Button variant="outlined" onClick={() => setActiveStep(6)}>
                  Continue to apply
                </Button>
              ) : null}
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 6 && isShipmentEvidence && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Apply to canonical facts (upsert)</Typography>
            {shipmentEvidencePollJobId != null &&
            importJobApplyIsLoaded(shipmentStageTrim, shipmentStatus) ? (
              <ImportJobLoadedSuccessCallout
                importJobId={shipmentEvidencePollJobId}
                templateLabel={selectedTemplate.display_name}
                fileName={shipmentImportJob?.file_name ?? jobDetail?.file_name}
                status={shipmentStatus}
                stage={shipmentStageTrim}
                factLayerLabel="inbound shipment facts (`fact_inbound_shipment`)"
                unresolvedNotes={shipmentApplyWarning ? [shipmentApplyWarning] : []}
                onStartNewImport={() => {
                  setActiveStep(0);
                  setSelectedSlug(null);
                  setSourceId('');
                  setLastJobId(null);
                  setLastGenericFile(null);
                  setHistoricalValidatedJobId(null);
                  setIsJobRevisitMode(false);
                  setShipmentApplyWarning(null);
                  void router.replace('/admin/imports');
                }}
                testId="shipment-import-loaded-success"
              />
            ) : (
              <>
                <Alert severity="warning">
                  Apply upserts inbound shipment facts using <strong>source_key</strong> (latest apply wins). Evidence from
                  each validate is preserved on the import job.
                </Alert>
                {shipmentApplyMut.isError ? (
                  <Alert severity="error">{safeDisplayError(shipmentApplyMut.error)}</Alert>
                ) : null}
                {shipmentApplyWarning ? (
                  <Alert severity="warning" onClose={() => setShipmentApplyWarning(null)}>
                    {shipmentApplyWarning}
                  </Alert>
                ) : null}
                {shipmentApplyMut.isPending ||
                (shipmentStatus === 'running' && shipmentStageTrim !== 'loaded') ? (
                  <LinearProgress data-testid="shipment-apply-running" />
                ) : null}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                  <Button onClick={() => setActiveStep(5)}>Back</Button>
                  <Button
                    variant="contained"
                    color="primary"
                    size="large"
                    disabled={shipmentApplyMut.isPending || shipmentStageTrim !== 'validated'}
                    onClick={() => void shipmentApplyMut.mutateAsync()}
                    data-testid="shipment-apply-import"
                  >
                    {shipmentApplyMut.isPending ? 'Applying…' : 'Apply import'}
                  </Button>
                  {shipmentStageTrim !== 'validated' && shipmentStageTrim !== 'loaded' ? (
                    <Typography variant="caption" color="text.secondary">
                      Apply unlocks when validation stage is <strong>validated</strong>.
                    </Typography>
                  ) : null}
                </Stack>
              </>
            )}
            {importJobApplyIsLoaded(shipmentStageTrim, shipmentStatus) ? (
              <Button onClick={() => setActiveStep(5)}>Back to validate &amp; resolve</Button>
            ) : null}
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
            <FormControl size="small" sx={{ maxWidth: 420 }}>
              <InputLabel id="dsi-workflow-mode-label">DSI workflow mode</InputLabel>
              <Select
                labelId="dsi-workflow-mode-label"
                label="DSI workflow mode"
                value={dsiWorkflowMode}
                onChange={(e) =>
                  setDsiWorkflowMode(e.target.value as 'auto' | 'historical' | 'weekly')
                }
              >
                <MenuItem value="auto">Auto — detect historical vs weekly from transaction dates</MenuItem>
                <MenuItem value="historical">Historical import (relaxed steward + auto-applies ready candidates after validate)</MenuItem>
                <MenuItem value="weekly">Weekly import (strict steward)</MenuItem>
              </Select>
            </FormControl>
            {!canGoUpload ? <Alert severity="warning">Complete provider, mode, and confirmations before uploading.</Alert> : null}
            <ImportFileUploadZone
              expanded
              onExpandedChange={() => {}}
              canUpload={!!canGoUpload}
              pending={upload.isPending}
              error={upload.isError ? safeDisplayError(upload.error) : null}
              onFile={onFile}
              subtitle="Or choose a file. Validation and apply run only after you confirm mappings."
              testIdPrefix="dsi-upload"
            />
            <Button
              variant="outlined"
              disabled={!canGoUpload || upload.isPending}
              onClick={() => setDsiBulkUploadOpen(true)}
              data-testid="dsi-bulk-upload-open"
            >
              Unified batch upload
            </Button>
            {typeof sourceId === 'number' ? (
              <DsiCoveragePanel
                sourceId={sourceId}
                onUploadHistorical={openDsiHistoricalBackfill}
              />
            ) : null}
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
            {!dsiIsMultiSheet && !dsiMappingState?.file_headers?.length ? (
              <Alert severity="warning">Loading column headers…</Alert>
            ) : null}
            {dsiIsMultiSheet && !dsiSheetKeys.length ? (
              <Alert severity="warning">Loading workbook sheets…</Alert>
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
            {dsiIsMultiSheet && dsiSheetKeys.length ? (
              <Stack spacing={2} data-testid="dsi-multi-sheet-mapping">
                <Alert severity="info">
                  {dsiMappingState?.multi_file
                    ? `Multi-file batch (${dsiSheetKeys.length} sheet${
                        dsiSheetKeys.length === 1 ? '' : 's'
                      } across files). Map each source once — same layout is shared.`
                    : `Multi-sheet workbook detected (${dsiSheetKeys.length} mappable sheet${
                        dsiSheetKeys.length === 1 ? '' : 's'
                      }). Map each sheet, then save.`}
                </Alert>
                <Tabs
                  value={dsiActiveSheetKey ?? dsiSheetKeys[0]}
                  onChange={(_e, v) => setDsiActiveSheetKey(String(v))}
                  variant="scrollable"
                  scrollButtons="auto"
                >
                  {dsiSheetKeys.map((key) => {
                    const sheetOk = dsiGateFromMapping(dsiNestedMapDraft[key] ?? {});
                    return (
                      <Tab
                        key={key}
                        value={key}
                        label={`${key}${sheetOk ? '' : ' *'}`}
                        data-testid={`dsi-sheet-tab-${key}`}
                      />
                    );
                  })}
                </Tabs>
                {(() => {
                  const activeKey = dsiActiveSheetKey ?? dsiSheetKeys[0];
                  const sheetMeta = (dsiMappingState?.dsi_workbook?.sheets ?? []).find(
                    (s) =>
                      s.mapping_key === activeKey ||
                      s.sheet_key === activeKey ||
                      `${s.source_file ?? ''}::${s.sheet_key ?? ''}` === activeKey
                  );
                  const headers =
                    sheetMeta?.columns?.length
                      ? sheetMeta.columns
                      : Object.keys(dsiNestedMapDraft[activeKey] ?? {});
                  const sheetState = dsiMappingState?.sheet_field_mappings?.[activeKey];
                  return (
                    <CanonicalColumnMappingPanel
                      testIdPrefix={`dsi-sheet-${activeKey}`}
                      fileHeaders={headers}
                      draft={dsiNestedMapDraft[activeKey] ?? {}}
                      onChange={(next) =>
                        setDsiNestedMapDraft((prev) => ({ ...prev, [activeKey]: next }))
                      }
                      targetOptions={dsiMappingTargetOptions}
                      columnSamples={sheetState?.column_samples ?? sheetMeta?.column_samples}
                      blockingErrors={sheetState?.blocking_mapping_errors}
                      adjustmentNotices={sheetState?.mapping_adjustment_notices}
                      requiredGroups={DSI_MAPPING_REQUIRED_GROUPS}
                      formatSamples={formatDsiSamples}
                      dirty={dsiMappingDraftDirty}
                    />
                  );
                })()}
              </Stack>
            ) : !dsiMappingState?.file_headers?.length ? null : (
              <CanonicalColumnMappingPanel
                testIdPrefix="dsi"
                fileHeaders={dsiMappingState.file_headers}
                draft={dsiMapDraft}
                onChange={(next) => setDsiMapDraft(next)}
                targetOptions={dsiMappingTargetOptions}
                columnSamples={dsiMappingState.column_samples}
                blockingErrors={dsiMappingState.blocking_mapping_errors}
                adjustmentNotices={dsiMappingState.mapping_adjustment_notices}
                requiredGroups={DSI_MAPPING_REQUIRED_GROUPS}
                formatSamples={formatDsiSamples}
                dirty={dsiMappingDraftDirty}
              />
            )}
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
            {typeof sourceId === 'number' ? (
              <DsiCoveragePanel
                sourceId={sourceId}
                flagsOnly
                onUploadHistorical={openDsiHistoricalBackfill}
              />
            ) : null}
            {lastJobId != null &&
            ((dsiMappingState?.dsi_workbook as { files?: string[] } | null | undefined)?.files?.length ||
              Object.keys(
                (
                  (dsiValidatePollJob?.staged_metadata ?? dsiJobIntelligence?.staged_metadata) as
                    | { dsi_file_row_subtotals?: Record<string, number> }
                    | undefined
                )?.dsi_file_row_subtotals ?? {}
              ).length) ? (
              <DsiFileReviewStrip
                jobId={lastJobId}
                filenames={
                  (dsiMappingState?.dsi_workbook as { files?: string[] } | null | undefined)?.files?.length
                    ? ((dsiMappingState?.dsi_workbook as { files?: string[] }).files as string[])
                    : Object.keys(
                        (
                          (dsiValidatePollJob?.staged_metadata ?? dsiJobIntelligence?.staged_metadata) as
                            | { dsi_file_row_subtotals?: Record<string, number> }
                            | undefined
                        )?.dsi_file_row_subtotals ?? {}
                      )
                }
                rowSubtotals={
                  (
                    (dsiValidatePollJob?.staged_metadata ?? dsiJobIntelligence?.staged_metadata) as
                      | { dsi_file_row_subtotals?: Record<string, number> }
                      | undefined
                  )?.dsi_file_row_subtotals ?? null
                }
                excludedFiles={
                  (
                    (dsiValidatePollJob?.staged_metadata ?? dsiJobIntelligence?.staged_metadata) as
                      | { dsi_excluded_files?: string[] }
                      | undefined
                  )?.dsi_excluded_files ?? null
                }
                jobLoaded={String(dsiMappingState?.stage ?? dsiValidatePollJob?.stage ?? '') === 'loaded'}
                onChanged={() => {
                  void refetchDsiMapping();
                  void qc.invalidateQueries({ queryKey: ['import-job', lastJobId] });
                  void qc.invalidateQueries({ queryKey: ['dsi-job-intelligence', lastJobId] });
                  void qc.invalidateQueries({ queryKey: ['dsi-async-validate-import-job', lastJobId] });
                }}
              />
            ) : null}
            {dsiJobFailedAlert}
            {!dsiServerMappingGateOk ? (
              <Alert severity="warning" data-testid="dsi-validate-blocked">
                Complete required column mappings on the previous step, then use <strong>Save mapping</strong> or{' '}
                <strong>Save &amp; continue to validate</strong> before running validation.
              </Alert>
            ) : null}
            {dsiPipelineInFlight ? (
              <DsiValidateProgressPanel
                progress={dsiProgress}
                isRunning={dsiPipelineInFlight || (dsiValidate.isPending ?? false)}
              />
            ) : dsiValidate.isPending ? (
              <LinearProgress />
            ) : null}
            {dsiValidate.isError ? <Alert severity="error">{safeDisplayError(dsiValidate.error)}</Alert> : null}
            {dsiIntelligenceState ? (
              <DsiIntelligenceStatusPanel intelligenceState={dsiIntelligenceState} />
            ) : null}
            {dsiValidationComplete && !dsiPipelineInFlight ? (
              <Alert
                severity={
                  distributorSiSummary != null && dsiHumanFixableBlockingRows(distributorSiSummary) > 0
                    ? 'warning'
                    : distributorSiSummary != null &&
                        ((distributorSiSummary.warning_rows ?? 0) > 0 ||
                          (distributorSiSummary.rows_inventory_ready_with_sellout_warnings ?? 0) > 0)
                      ? 'warning'
                      : 'success'
                }
                data-testid="dsi-validate-finished"
              >
                {distributorSiSummary != null && dsiHumanFixableBlockingRows(distributorSiSummary) > 0 ? (
                  'Validation finished with steward-map blockers. Resolve unmapped customers below, or merge master-data alias conflicts on the duplicates page, then re-run validation before applying.'
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
                  <strong>{dsiHumanFixableBlockingRows(distributorSiSummary)}</strong> steward-map blocking;{' '}
                  <strong>{distributorSiSummary.warning_rows ?? 0}</strong> warnings;{' '}
                  <strong>{distributorSiSummary.aggregated_candidates ?? 0}</strong> aggregated mapping candidate groups.
                </Typography>
                {formatDsiBlockerSummaryLine(distributorSiSummary) ? (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    Blocker split: {formatDsiBlockerSummaryLine(distributorSiSummary)}
                  </Typography>
                ) : null}
                {(distributorSiSummary?.aggregated_candidates ?? 0) > 0 ? (
                  <Typography variant="caption" color="text.secondary" display="block">
                    Resolve grouped tokens below on this page (paginated), or open the global{' '}
                    <Link component={NextLink} href={`/admin/mappings?import_job_id=${lastJobId}`}>
                      Mapping queue (legacy)
                    </Link>{' '}
                    ({distributorSiSummary?.aggregated_candidates ?? 0} group
                    {(distributorSiSummary?.aggregated_candidates ?? 0) !== 1 ? 's' : ''} for this job).
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
            {lastJobId != null && dsiValidationComplete ? (
              <DsiImportJobResolutionSection
                importJobId={lastJobId}
                validateSummary={distributorSiSummary}
                dsiPipelineRunning={dsiPipelineInFlight}
                onAsyncPipelineStarted={handleDsiAsyncPipelineStarted}
                onInvalidate={() => {
                  void refetchPreview();
                }}
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
              <Button onClick={() => setActiveStep(5)} disabled={dsiValidate.isPending || dsiPipelineInFlight}>
                Back
              </Button>
              {dsiCanContinueToApply ? (
                <>
                  <Button
                    variant="outlined"
                    onClick={() => void dsiValidate.mutateAsync()}
                    disabled={dsiValidate.isPending || dsiPipelineInFlight || !dsiServerMappingGateOk}
                    data-testid="dsi-rerun-validation"
                  >
                    {dsiValidate.isPending || dsiPipelineInFlight ? 'Validating…' : 'Re-run validation'}
                  </Button>
                  <Button variant="contained" onClick={() => setActiveStep(7)} data-testid="dsi-continue-to-apply">
                    Continue to apply
                  </Button>
                </>
              ) : (
                <Button
                  variant="contained"
                  onClick={() => void dsiValidate.mutateAsync()}
                  disabled={dsiValidate.isPending || dsiPipelineInFlight || !dsiServerMappingGateOk}
                  data-testid="dsi-run-validation"
                >
                  {dsiValidate.isPending || dsiPipelineInFlight
                    ? 'Validating…'
                    : dsiHasValidateResult
                      ? 'Re-run validation'
                      : 'Run validation'}
                </Button>
              )}
            </Stack>
          </Stack>
        ) : null}

        {activeStep === 7 && isDsi && selectedTemplate ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">Apply to canonical facts (upsert)</Typography>
            {importJobApplyIsLoaded(dsiJobSnapshotForRouting.stage, dsiJobSnapshotForRouting.status) ? (
              <ImportJobLoadedSuccessCallout
                importJobId={lastJobId ?? 0}
                templateLabel={selectedTemplate.display_name}
                fileName={jobDetail?.file_name}
                status={dsiJobSnapshotForRouting.status}
                stage={dsiJobSnapshotForRouting.stage}
                factLayerLabel="distributor sell-out & inventory facts (`fact_sales_sellout`, `fact_inventory_distributor`)"
                onStartNewImport={() => {
                  setActiveStep(0);
                  setSelectedSlug(null);
                  setSourceId('');
                  setLastJobId(null);
                  setLastGenericFile(null);
                  setHistoricalValidatedJobId(null);
                  setIsJobRevisitMode(false);
                  setDsiValidateAsync(false);
                  setDsiApplyAsync(false);
                  void router.replace('/admin/imports');
                }}
                testId="dsi-import-loaded-success"
              />
            ) : (
              <>
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
            {dsiApplyComplete.isError ? (
              <Alert severity="error">{safeDisplayError(dsiApplyComplete.error)}</Alert>
            ) : null}
            {dsiApply.isPending || dsiApplyComplete.isPending || dsiApplyAsync ? <LinearProgress /> : null}
            {dsiApplyAsync ? (
              <Alert severity="info" data-testid="dsi-apply-running">
                Applying facts and finalizing to <strong>loaded</strong> in the background worker. This can take a few
                minutes for large files — you can leave this page and the job will continue.
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button onClick={() => setActiveStep(6)}>Back</Button>
              <Button
                variant="contained"
                color="primary"
                disabled={
                  dsiApply.isPending ||
                  dsiApplyComplete.isPending ||
                  dsiApplyAsync ||
                  (selectedTemplate.destructive_apply_requires_confirm && !confirmDestructive)
                }
                onClick={() => void dsiApply.mutateAsync()}
              >
                Apply
              </Button>
              {dsiCanFinalizeToLoaded ? (
                <Button
                  variant="outlined"
                  color="success"
                  disabled={dsiApply.isPending || dsiApplyComplete.isPending || dsiApplyAsync}
                  onClick={() => void dsiApplyComplete.mutateAsync()}
                  data-testid="dsi-apply-complete"
                >
                  Finalize to loaded
                </Button>
              ) : null}
            </Stack>
            {dsiCanFinalizeToLoaded ? (
              <Alert severity="info" data-testid="dsi-apply-complete-hint">
                After stewards clear blocked staging lines and facts apply cleanly, use <strong>Finalize to loaded</strong>{' '}
                to re-resolve rows, run fact upserts, and set the job to <strong>loaded</strong>.
              </Alert>
            ) : null}
              </>
            )}
          </Stack>
        ) : null}

        {activeStep === 4 && !isPm && !isDsi && !isShipmentEvidence ? (
          <Stack spacing={2}>
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
            <ImportFileUploadZone
              expanded
              onExpandedChange={() => {}}
              canUpload={!!canGoUpload}
              pending={upload.isPending}
              error={upload.isError ? safeDisplayError(upload.error) : null}
              onFile={onFile}
              subtitle="Or choose a file. Pipeline runs according to import mode."
              testIdPrefix="generic-upload"
            />
            {upload.isSuccess && lastJobId != null && upload.data?.import_mode !== 'apply' ? (
              <Alert severity="success">
                Job <strong>#{lastJobId}</strong> created.{' '}
                <Button size="small" onClick={() => void refetchPreview()}>
                  Refresh validation preview
                </Button>
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
          isLoading={jobsLoading && jobs == null}
          isError={jobsIsError}
          error={importJobsListError}
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

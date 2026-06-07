export type DsiGeoStewardBulkAction = 'register_region_from_hint' | 'register_from_file';

export type DsiGeoStewardBulkItem = {
  kind: 'channel' | 'region';
  raw_token: string;
  normalized_token?: string | null;
  code?: string | null;
  name?: string | null;
  iso_alpha2?: string | null;
};

export type DsiGeoStewardBulkApplyResponse = {
  import_job_id: number;
  action: DsiGeoStewardBulkAction;
  applied: number;
  failed: number;
  results: Array<Record<string, unknown>>;
};

export type DsiBulkAction =
  | 'ignore'
  | 'map_customer'
  | 'map_distributor'
  | 'resolve_product'
  | 'create_provisional_customer'
  | 'create_provisional_distributor'
  | 'set_plan_fallback_region'
  | 'set_plan_fallback_channel'
  | 'apply_suggested_region';

export type DsiCatalogOpt = { id: number; code: string; name: string };

/** Resolution-plan apply feedback shown above the steward workspace. */
export type PlanApplyFeedback = {
  message: string;
  severity: 'success' | 'error';
};

export type DsiUnresolvedGeoRowDto = {
  dimension: string;
  normalized_token: string;
  raw_token: string;
  resolution_detail: string;
  candidate_ids: number[];
  row_count: number;
  geographic_hint?: {
    guessed_region_code: string;
    matched_catalog: boolean;
    region_id: number | null;
    alias_registered?: boolean;
    registered_region_id?: number | null;
  };
};

export type DsiRegionEvidenceDto = {
  suggested_region_id: number | null;
  confidence: number;
  explanation_summary: string;
  explanation_factors: Array<Record<string, unknown>>;
  channel_geographic_hints: Array<Record<string, unknown>>;
  province_evidence: Record<string, unknown>;
};

export type DsiBulkPreviewResponse = {
  import_job_id: number;
  action: DsiBulkAction;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

export type DsiBulkApplyResponse = {
  import_job_id: number;
  action: DsiBulkAction;
  applied: number;
  failed: number;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

export type DsiBulkProvisionalAsyncEnqueueResponse = {
  import_job_id: number;
  task_id: string;
  async_poll: boolean;
  action: DsiBulkAction;
};

export type DsiBulkTaskStatusResponse = {
  import_job_id: number;
  task_id: string;
  state: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  result?: DsiBulkApplyResponse;
  error?: string;
};

export type DsiPlanRowOverride = {
  action?: string;
  target_id?: number | null;
  region_id?: number | null;
  channel_id?: number | null;
  hold_for_manual_review?: boolean;
  ack_strategic_channel_hint?: boolean;
  confirm_for_suspicious_distributor_token?: boolean;
  confirm_ineligible_product?: boolean;
  audit_note?: string | null;
};

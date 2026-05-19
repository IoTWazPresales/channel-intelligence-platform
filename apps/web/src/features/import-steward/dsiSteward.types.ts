export type DsiBulkAction =
  | 'ignore'
  | 'map_customer'
  | 'map_distributor'
  | 'resolve_product'
  | 'create_provisional_customer'
  | 'create_provisional_distributor';

export type DsiCatalogOpt = { id: number; code: string; name: string };

export type DsiUnresolvedGeoRowDto = {
  dimension: string;
  normalized_token: string;
  raw_token: string;
  resolution_detail: string;
  candidate_ids: number[];
  row_count: number;
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

/** Shared progress shapes for import-job Celery tasks (DSI pipeline, bulk provisional, etc.). */

export type ImportJobPipelineProgress = {
  job_id?: number;
  stage?: string;
  status?: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  task_state?: string | null;
  pipeline_queued_at?: string | null;
  pipeline_started_at?: string | null;
  progress_at?: string | null;
  /** Durable validate upfront sub-step (from ``staged_metadata.dsi_validate_sub_phase``). */
  sub_phase?: string | null;
};

export type BulkProvisionalTaskProgress = {
  import_job_id: number;
  task_id: string;
  state: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  error?: string;
  /** Present on SUCCESS for bulk provisional / plan apply / compute tasks. */
  result?: unknown;
};

export type BackgroundTaskKind =
  | 'dsi_pipeline'
  | 'dsi_bulk_provisional'
  | 'dsi_bulk_ignore'
  | 'dsi_resolution_plan_apply'
  | 'dsi_resolution_plan_compute'
  | 'shipment_import'
  | 'shipment_bulk'
  | 'product_master_commit'
  | 'product_master_validate'
  | 'commercial_planner_lineup_parse'
  | 'cpor_historical_import'
  | 'cpor_resolution_plan'
  | 'cst_resolution_plan'
  | 'cst_bulk';

export type BackgroundTaskStatus = 'running' | 'succeeded' | 'failed';

export type BackgroundTaskRecord = {
  task_id: string;
  import_job_id: number;
  kind: BackgroundTaskKind;
  label: string;
  status: BackgroundTaskStatus;
  template_slug?: string | null;
  file_name?: string | null;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  task_state?: string | null;
  polled_at?: string;
  can_retry?: boolean;
};

export type BackgroundTasksListResponse = {
  tasks: BackgroundTaskRecord[];
  count: number;
  active_count?: number;
};

export type CancelImportJobResponse = {
  cancelled: boolean;
  job_id: number;
  previous_status: string;
};

export type RetryImportJobResponse = {
  queued: boolean;
  job_id: number;
  task_id: string | null;
};

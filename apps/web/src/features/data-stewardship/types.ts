export type StewardshipSummary = {
  database: string;
  tenant_id: string;
  jobs_last_7d: number;
  jobs_iso_week: number;
  failed_7d: number;
  failed_all: number;
  completed_7d: number;
  completed_all: number;
  pending_7d: number;
  pending_all: number;
  jobs_unarchived: number;
  templates_enabled: number;
  templates_visible_non_admin: number;
  legacy_queue_open: number;
  candidates_needs_review: number;
  candidates_customerish: number;
  candidates_productish: number;
  candidates_distributorish: number;
  products: number;
  customers: number;
  customers_unverified: number;
  distributors: number;
  distributors_unverified: number;
  stores: number;
  audit_events: number;
  labels: Record<string, string>;
  captions: Record<string, string>;
};

export type StewardQueueGroup = {
  entity_type: string;
  label: string;
  candidate_count: number;
  job_count: number;
  row_count: number;
  covered: boolean;
};

export type StewardQueueItem = {
  id: number;
  entity_type: string;
  label: string;
  normalized_key: string;
  row_count: number;
  total_units: number | null;
  status: string;
  import_job_id: number;
  template_slug: string | null;
  file_name: string | null;
  job_status: string | null;
  steward_href: string | null;
  covered: boolean;
  memory_state?: 'unknown' | 'remembered' | 'conflict';
};

export type StewardFailureQueueResponse = {
  database: string;
  tenant_id: string;
  open_status: string;
  groups: StewardQueueGroup[];
  items: StewardQueueItem[];
  total_candidates: number;
  distinct_jobs: number;
  remembered_count?: number;
  include_remembered?: boolean;
  returned: number;
  truncated: boolean;
  entity_type_filter: string | null;
};

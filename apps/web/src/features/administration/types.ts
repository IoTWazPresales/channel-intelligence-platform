export type AdminOperationRow = {
  id: number;
  template_slug: string | null;
  status: string;
  stage: string;
  file_name: string;
  error_summary: string | null;
};

export type AdministrationOverview = {
  database: string;
  tenant_id: string;
  data_unavailable: boolean;
  users: number;
  users_by_role: Record<string, number>;
  jobs_running: number;
  jobs_pending: number;
  failed_24h: number;
  failed_open: number;
  sql_queries_7d: number;
  sql_queries_all: number;
  operations: AdminOperationRow[];
  labels: Record<string, string>;
  captions: Record<string, string>;
};

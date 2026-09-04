import type { SettleReadiness } from '@/features/cpor/fxDisplay';

export type CporCaseListRow = {
  id: number;
  case_code: string;
  case_name?: string | null;
  customer_id?: number;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  workflow_status: string;
  origin?: string | null;
  currency_code?: string;
  roe_snapshot?: number | null;
  missing_roe?: boolean;
  line_count?: number;
  estimate_qty_sum?: number | null;
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  settle_readiness?: SettleReadiness;
  outstanding_amount?: number | null;
  owed_amount?: number | null;
  flags?: string[];
};

export type CporCasesPage = {
  items: CporCaseListRow[];
  total: number;
  page: number;
  page_size: number;
  status_counts?: Record<string, number>;
};

export type CporCaseLine = {
  id: number;
  product_id: number;
  product_sku: string | null;
  product_name: string | null;
  distributor_id: number | null;
  pod_quarter: string | null;
  srp: number;
  vat_rate: number;
  dealer_margin_pct: number;
  margin_source: string;
  cost_basis: number | null;
  cost_source: string | null;
  estimate_qty: number;
  dealer_price: number | null;
  support_unit: number | null;
  ttl_support: number | null;
  flags: string[];
};

export type CporCaseDetail = {
  id: number;
  case_code: string;
  case_name?: string | null;
  customer_id?: number;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  workflow_status: string;
  origin?: string | null;
  currency_code?: string;
  roe_snapshot: number | null;
  missing_roe: boolean;
  allowed_next: string[];
  lines: CporCaseLine[];
  flags: string[];
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  created_by?: string | null;
};

export type SupportBiasRead = {
  reservation_source?: string;
  totals?: {
    planned_usd?: number | null;
    actual_usd?: number | null;
    bias_pct?: number | null;
  };
  data_unavailable?: boolean;
};

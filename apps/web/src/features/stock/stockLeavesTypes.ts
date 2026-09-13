export type StockLeavesHonesty = {
  database?: string;
  tenant_id?: string;
  data_unavailable?: boolean;
  today_sast?: string | null;
  sellthrough?: {
    current_iso_week?: string;
    current_week_label?: string;
    current_week_rows?: number;
    latest_iso_week?: string | null;
    latest_week_label?: string;
    latest_period_start?: string | null;
    latest_period_rows?: number;
    latest_customers?: string[];
    title?: string;
    body?: string;
    window_complete?: boolean;
  };
  forecast?: {
    trailing_weeks?: number;
    trailing_needed?: number;
    latest_iso_week?: string | null;
    latest_week_label?: string;
    latest_transaction_date?: string | null;
    forecast_rows?: number;
    title?: string;
    body?: string;
    window_complete?: boolean;
  };
};

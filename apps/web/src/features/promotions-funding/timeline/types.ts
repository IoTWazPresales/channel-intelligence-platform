export type CalendarKind = 'campaign' | 'pillar' | 'other';
export type Promotion = {
  case_id: number; case_code: string; case_name: string | null; promotion_type: string;
  status: string; customer_id: number; window_start: string; window_end: string;
};
export type CalendarEvent = {
  id: number; customer_id: number; name: string; kind: CalendarKind;
  start_date: string; end_date: string; source_file: string | null; upload_id: string;
};
export type Clash = {
  case_id: number; case_code: string; case_name: string | null; event_id: number;
  event_name: string; event_kind: CalendarKind; overlap_start: string; overlap_end: string; overlap_days: number;
};
export type Timeline = {
  customer?: { id: number; name: string }; from: string | null; to: string | null;
  promotions: Promotion[]; calendar_events: CalendarEvent[]; clashes: Clash[];
  data_unavailable?: boolean; customer_not_reporting?: boolean; message?: string;
};
export type CalendarProfile = {
  /** null for the computed generic default that has not been saved (it cannot be edited or deleted). */
  id: number | null; profile_code: string; display_name: string; header_row_index: number;
  sheet_name: string | null; column_map_json: Record<string, string[]>;
  value_maps_json: { kind?: Record<string, CalendarKind> }; is_default: boolean; notes: string | null;
};
export type CalendarPreview = {
  ok: boolean; filename: string; profile_code: string; upload_id: string; file_sha256: string;
  headers: string[]; mapped_columns: Record<string, string>; parsed_rows: number;
  blocking_errors: { code: string; message: string }[];
  row_errors: { row: number; code: string; message: string }[];
  will_insert: number; will_replace: number; events_truncated: boolean;
  customers: { customer_id: number; customer_name: string; events: number }[];
  unresolved_customers: { token: string; rows: number }[];
  events: { row_number: number; name: string; kind: CalendarKind; start_date: string; end_date: string }[];
};

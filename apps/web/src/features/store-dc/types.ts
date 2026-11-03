export type StoreMapLine = {
  product_id: number;
  sku: string | null;
  product_name: string | null;
  units: number;
  stock_on_hand: number | null;
  weeks_of_cover: number | null;
};

export type StoreMapStore = {
  customer_id: number;
  customer_name: string | null;
  site_label: string;
  latitude: number | null;
  longitude: number | null;
  pinned: boolean;
  last_week_units: number;
  stock_on_hand: number | null;
  weeks_of_cover: number | null;
  sell_through: number | null;
  lines: StoreMapLine[];
};

export type StoreMapCustomer = { id: number; code: string; name: string };

export type StoreMapPayload = {
  customers: StoreMapCustomer[];
  stores: StoreMapStore[];
  legend: { formula: string; best: string; worst: string };
};

export type NeedLine = {
  product_id: number;
  sku: string | null;
  product_name: string | null;
  stock_on_hand: number | null;
  weekly_rate: number | null;
  weeks_of_cover: number | null;
  need_units: number | null;
  need_reason: string;
  lead_time_label: string;
  slow: boolean;
  unsold: boolean;
  suggestions: string[];
  suggestion_executed: boolean;
};

export type SiteBlock = {
  site_label: string | null;
  customer_id: number;
  customer_name: string;
  supply: string;
  stock_on_hand: number | null;
  need_units: number | null;
  lead_time_label: string;
  lines: NeedLine[];
};

export type LeadLeg = {
  leg: string;
  title: string;
  history: string;
  sample_count: number;
  min_days: number | null;
  p25_days: number | null;
  median_days: number | null;
  p75_days: number | null;
  max_days: number | null;
  histogram: { bucket: string; count: number }[];
  lead_time_label: string;
  note?: string;
};

export type ReplenishmentViewData = {
  customer_id: number;
  customer_name: string;
  customer_code: string;
  grain: string;
  cover: { min_weeks: number; target_weeks: number; source: string };
  dc_sections: {
    candidate_id: number;
    site_label: string;
    stock_on_hand: number | null;
    stock_note: string | null;
    serves: { customer_id: number; customer_name: string | null }[];
    lead_time: LeadLeg;
    onward: LeadLeg;
    stores: SiteBlock[];
    need_from_distributor: {
      product_id: number;
      sku: string | null;
      stock_on_hand: number | null;
      need_units: number | null;
      need_reason: string;
      lead_time_label: string;
      stores_asking: number;
    }[];
  }[];
  sites: SiteBlock[];
  account: SiteBlock | null;
  collapsed_grain: { units_sold: number; note: string } | null;
  lead_times: {
    distributor_id: number;
    distributor_name: string | null;
    receiving_site: string | null;
    inbound: LeadLeg;
    onward: LeadLeg;
  }[];
  lead_time_min_deliveries: number;
};

export type SiteCandidateRow = {
  id: number;
  customer_id: number | null;
  customer_name: string | null;
  site_label: string;
  evidence_kind: string;
  status: string;
  blocked_as_distributor_site: boolean;
};

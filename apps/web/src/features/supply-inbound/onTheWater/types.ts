/** Payload of GET /api/v1/shipping/on-the-water (apps/api/app/services/shipping/on_the_water.py). */

export type MoneyPart = { currency: string; amount: number };
export type NamedUnits = { name: string; units: number };

export type Vessel = {
  id: string;
  /** Opaque key the grid filter understands (`vessel` query parameter). */
  key: string;
  inferred: boolean;
  vessel_name: string | null;
  forwarder: string;
  lane_id: string;
  lane_label: string;
  route_assumed: boolean;
  deliver_port: string | null;
  on_board: string | null;
  eta: string | null;
  days_to_eta: number | null;
  overdue: boolean;
  days_overdue: number;
  /** Share of on-board to ETA elapsed, 0..100. */
  pct: number;
  units: number;
  lines: number;
  deliveries: number;
  amount: MoneyPart[];
  distributors: NamedUnits[];
  products: NamedUnits[];
  more_models: number;
  slip_days: number;
  history: { first_eta: string | null; first_report: string | null; current_eta: string | null; latest_report: string | null };
  /** Position on the map in percent of its width and height. */
  x: number;
  y: number;
};

export type PortCondition = {
  id: number;
  port_code: string;
  label: string;
  delay_days: number;
  note: string | null;
  entered_by: string;
  entered_at: string | null;
};

export type PortRow = { code: string; label: string; waiting_units: number; condition: PortCondition | null };

export type NeedsLook = {
  lines: number;
  units: number;
  distributors: NamedUnits[];
  since: string | null;
  days: number;
  on_board_moved: { from: string | null; to: string | null } | null;
};

export type OnTheWaterData = {
  as_of: string;
  report_date: string | null;
  report_age_days: number | null;
  report_stale: boolean;
  stale_report_days: number;
  reports: { count: number; earlier: number; since: string | null };
  tiles: {
    at_sea: { units: number; lines: number; vessels: number; amount: MoneyPart[]; air_units: number; overdue_vessels: number };
    arrived: { units: number; lines: number; by_port: NamedUnits[] };
    booked: { units: number; lines: number };
    eta_moved: { vessels_moved: number; vessels: number; min_days: number; max_days: number; since: string | null };
  };
  vessels: Vessel[];
  map: {
    size: [number, number];
    lanes: Array<{ id: string; kind: 'sea' | 'leg'; d: string }>;
    ports: Array<{ id: string; label: string; x: number; y: number }>;
    cluster_radius_pct: number;
  };
  port_rows: PortRow[];
  needs_look: NeedsLook | null;
  position_note: string;
};

/** Wire types for the new-customer line-up proposal (API: lineup_new_customer.py). */

export type SeedSource = 'pm_bottom_cost' | 'previous_lineups';

/** Which history a previous-line-ups proposal used: the customer's own, or the master line-up. */
export type SeedFallback = 'customer_own' | 'master';

export type ProposalEvidence =
  | { kind: 'pm_bottom_cost'; pm_bottom_cost: number; currency: string | null }
  | { kind: 'previous_lineups'; scope: SeedFallback; periods: string[] };

export type ProposalLine = {
  product_id: number;
  sku: string;
  label: string;
  seed_source: SeedSource;
  evidence: ProposalEvidence;
};

export type Proposal = {
  customer: { id: number; code: string; name: string };
  period_start: string;
  period_label: string;
  source: SeedSource;
  /** Null for the PM bottom cost source. */
  fallback: SeedFallback | null;
  periods_used: string[];
  basis: string;
  line_count: number;
  lines: ProposalLine[];
};

export type ReportingCustomer = { id: number; name: string };

export type ApproveBody = {
  source: SeedSource;
  period_start: string;
  product_ids: number[];
};

export type ApproveResult = {
  approved_count: number;
  commercial_case_id: number;
  period_label: string;
  created: { item_id: number; product_id: number; sku: string }[];
};

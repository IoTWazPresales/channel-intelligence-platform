export type ExceptionType =
  | 'stockout_risk'
  | 'overstock_risk'
  | 'delayed_inbound'
  | 'forecast_deviation'
  | 'price_conflict'
  | 'promo_not_ready'
  | 'mapping_issue'
  | 'competitor_undercut'
  | 'budget_gap';

export type UserRole =
  | 'admin'
  | 'data_steward'
  | 'commercial_manager'
  | 'planner'
  | 'product_manager'
  | 'finance_reviewer'
  | 'executive_viewer';

export interface NavItem {
  label: string;
  href: string;
  roles?: UserRole[];
  section?: string;
}

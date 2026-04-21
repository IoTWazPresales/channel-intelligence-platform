/** Pure helpers for Product Master column mapping draft (keeps UI + tests aligned with API). */

export type PmDisposition = 'ignore' | 'stage_raw' | 'attribute_candidate';

export type PmColumnDraft = {
  header: string;
  /** Canonical field key, or empty when unmapped. */
  target: string;
  disposition: PmDisposition;
};

export type MapperAction =
  | 'auto_map'
  | 'suggest'
  | 'recommend_stage_metadata'
  | 'recommend_ignore'
  | 'no_strong_suggestion';

export type PmHeaderSuggestion = {
  target?: string;
  suggested_target?: string;
  mapper_action?: MapperAction | string;
  recommended_disposition?: 'stage_raw' | 'ignore';
  from_source_memory?: boolean;
  disposition?: string;
  confidence?: number;
  reasons?: string[];
  runner_up?: { target?: string; confidence?: number; reasons?: string[] } | null;
  hint_target?: string;
};

export function initPmColumnDrafts(
  headers: string[],
  suggested: Record<string, PmHeaderSuggestion> | null | undefined,
  saved: Record<string, PmHeaderSuggestion> | null | undefined
): PmColumnDraft[] {
  const src = saved && Object.keys(saved).length > 0 ? saved : suggested;
  return headers.map((h) => {
    const m = src?.[h];
    const action = m?.mapper_action;
    const autoFillTarget =
      m?.target &&
      String(m.target).trim() &&
      (action === 'auto_map' || action === undefined || action === null || action === '');
    if (autoFillTarget) {
      return { header: h, target: String(m.target).trim(), disposition: 'ignore' };
    }
    if (m?.mapper_action === 'recommend_stage_metadata' && m.recommended_disposition === 'stage_raw') {
      return { header: h, target: '', disposition: 'stage_raw' };
    }
    if (m?.mapper_action === 'recommend_ignore' && m.recommended_disposition === 'ignore') {
      return { header: h, target: '', disposition: 'ignore' };
    }
    const d = (m?.disposition as PmDisposition | undefined) || 'ignore';
    const disposition: PmDisposition =
      d === 'stage_raw' || d === 'attribute_candidate' || d === 'ignore' ? d : 'ignore';
    return { header: h, target: '', disposition };
  });
}

export function pmDraftsToApiColumns(drafts: PmColumnDraft[]): { header: string; target?: string | null; disposition?: string | null }[] {
  return drafts.map((c) => {
    if (c.target.trim()) {
      return { header: c.header, target: c.target.trim(), disposition: null };
    }
    return { header: c.header, target: null, disposition: c.disposition };
  });
}

/** Groups for ordering mapping-target dropdown sections (matches API `field_definitions.group`). */
export const PM_GROUP_ORDER = [
  'required_core',
  'product_identity',
  'commercial_identity',
  'classification',
  'lifecycle',
  'barcode',
  'catalog_identity',
  'optional',
] as const;

export const PM_GROUP_LABEL: Record<string, string> = {
  required_core: 'Required core fields',
  product_identity: 'Product identity',
  commercial_identity: 'Commercial identity',
  classification: 'Classification',
  lifecycle: 'Lifecycle',
  barcode: 'Barcode identifiers',
  catalog_identity: 'Catalog / source identity',
  optional: 'Optional',
};

export type PmFieldDefinition = {
  key: string;
  group: string;
  label: string;
  importance: string;
  dim_persistence: string;
  description: string;
  /** technical | commercial | classification | lifecycle | barcode | source | product */
  role?: string;
};

export function sortPmFieldDefinitions(defs: PmFieldDefinition[]): PmFieldDefinition[] {
  return [...defs].sort((a, b) => {
    const ia = PM_GROUP_ORDER.indexOf(a.group as (typeof PM_GROUP_ORDER)[number]);
    const ib = PM_GROUP_ORDER.indexOf(b.group as (typeof PM_GROUP_ORDER)[number]);
    const sa = ia === -1 ? 99 : ia;
    const sb = ib === -1 ? 99 : ib;
    if (sa !== sb) return sa - sb;
    return a.label.localeCompare(b.label);
  });
}

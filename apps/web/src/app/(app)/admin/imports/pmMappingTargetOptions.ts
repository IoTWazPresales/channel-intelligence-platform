/**
 * Product Master mapping target picker: ordering, badges, duplicate awareness.
 */

import { createFilterOptions } from '@mui/material/Autocomplete';
import type { PmFieldDefinition } from './pmMappingHelpers';

export type TargetUsageByKey = Record<string, string[]>;

/** Map each canonical target → file column headers currently mapped to it. */
export function buildTargetUsageMap(
  columns: { header: string; target: string }[]
): TargetUsageByKey {
  const m: TargetUsageByKey = {};
  for (const c of columns) {
    const t = c.target.trim();
    if (!t) continue;
    if (!m[t]) m[t] = [];
    m[t].push(c.header);
  }
  return m;
}

export type EnrichedPmTargetOption = PmFieldDefinition & {
  sortTier: number;
  sectionKey: string;
  sectionLabel: string;
  badgeTexts: string[];
  duplicateFromHeaders: string[];
};

function roleBadges(role: string | undefined, dim: string | undefined): string[] {
  const badges: string[] = [];
  if (dim === 'canonical') badges.push('Canonical');
  if (dim === 'catalog_only') badges.push('Catalog-only');
  const r = role ?? '';
  if (r === 'commercial') badges.push('Commercial');
  else if (r === 'barcode') badges.push('Barcode');
  else if (r === 'lifecycle') badges.push('Lifecycle');
  else if (r === 'technical') badges.push('Technical');
  else if (r === 'classification') badges.push('Classification');
  else if (r === 'product') badges.push('Product identity');
  else if (r === 'source') badges.push('Source');
  return badges;
}

export function enrichPmMappingTargets(params: {
  defs: PmFieldDefinition[];
  requiredFields: string[];
  identityTargets: string[];
  usage: TargetUsageByKey;
  currentHeader: string;
}): EnrichedPmTargetOption[] {
  const { defs, requiredFields, identityTargets, usage, currentHeader } = params;
  const reqSet = new Set(requiredFields);
  const idSet = new Set(identityTargets);

  return defs.map((d) => {
    const users = usage[d.key] ?? [];
    const duplicateFromHeaders = users.filter((h) => h !== currentHeader);
    const selfUses = users.includes(currentHeader);

    let sortTier = 35;
    let sectionKey = 'other';
    let sectionLabel = 'Other targets';

    if (duplicateFromHeaders.length > 0) {
      sortTier = 80;
      sectionKey = 'duplicate';
      sectionLabel = 'Already mapped in this file';
    } else if ((reqSet.has(d.key) || idSet.has(d.key)) && users.length === 0) {
      sortTier = 0;
      sectionKey = 'required_missing';
      sectionLabel = 'Required / identity — still needed';
    } else if ((reqSet.has(d.key) || idSet.has(d.key)) && selfUses && users.length === 1) {
      sortTier = 5;
      sectionKey = 'required_this_row';
      sectionLabel = 'Required — selected for this column';
    } else if (d.importance === 'high' && users.length === 0) {
      sortTier = 15;
      sectionKey = 'important_free';
      sectionLabel = 'Important — not yet mapped';
    } else if (d.importance === 'medium' && users.length === 0) {
      sortTier = 25;
      sectionKey = 'optional_free';
      sectionLabel = 'Other fields — available';
    } else if (users.length === 0) {
      sortTier = 30;
      sectionKey = 'other_free';
      sectionLabel = 'Other fields — available';
    }

    const badgeTexts: string[] = [];
    if (reqSet.has(d.key) || idSet.has(d.key)) badgeTexts.push('Required');
    if (d.importance === 'high') badgeTexts.push('Important');
    badgeTexts.push(...roleBadges(d.role, d.dim_persistence));

    if (duplicateFromHeaders.length > 0) {
      badgeTexts.push(`Also: ${duplicateFromHeaders.join(', ')}`);
    }

    return {
      ...d,
      sortTier,
      sectionKey,
      sectionLabel,
      badgeTexts,
      duplicateFromHeaders,
    };
  });
}

const baseFilter = createFilterOptions<EnrichedPmTargetOption>();

export function filterAndSortPmTargets(
  options: EnrichedPmTargetOption[],
  state: Parameters<typeof baseFilter>[1]
): EnrichedPmTargetOption[] {
  const filtered = baseFilter(options, state);
  const input = (state.inputValue ?? '').trim().toLowerCase();
  const scored = filtered.map((o) => {
    const label = `${o.label} ${o.key}`.toLowerCase();
    const exact = input && (o.key === input || o.label.toLowerCase() === input);
    const substr = input && label.includes(input);
    let bump = 0;
    if (exact) bump = -4;
    else if (substr) bump = -2;
    return { o, score: o.sortTier + bump };
  });
  scored.sort((a, b) => {
      if (a.score !== b.score) return a.score - b.score;
      return a.o.label.localeCompare(b.o.label);
    });
  return scored.map((x) => x.o);
}

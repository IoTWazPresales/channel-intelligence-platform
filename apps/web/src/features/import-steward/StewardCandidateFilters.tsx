'use client';

import { Button, Chip, Stack, Typography } from '@mui/material';
import type {
  StewardCandidateFilterState,
  StewardEntityFilter,
  StewardPartyFilter,
  StewardQueueFilter,
} from './stewardCandidateFilterLogic';
import { defaultStewardCandidateFilterState, stewardFiltersAreDefault } from './stewardCandidateFilterLogic';

export function StewardCandidateFilters({
  filters,
  onChange,
  visibleCount,
  totalCount,
  hideEntityFilter = false,
  hidePartyFilter = false,
  clearToDefault,
  isAtDefault,
  showProductMatchStatusChips = false,
  productMatchStatusCounts,
  hideProvisionalQueue = false,
  hideMatchToggles = false,
}: {
  filters: StewardCandidateFilterState;
  onChange: (next: StewardCandidateFilterState) => void;
  visibleCount: number;
  totalCount: number;
  /** When true, entity is fixed by the active tab (tabbed resolution workspace). */
  hideEntityFilter?: boolean;
  /** Hide Bill To / Ship To when not on the Distributors tab. */
  hidePartyFilter?: boolean;
  /** Tab-aware clear target; defaults to global all-entity state when omitted. */
  clearToDefault?: () => StewardCandidateFilterState;
  /** Tab-aware default check; falls back to global default when omitted. */
  isAtDefault?: (filters: StewardCandidateFilterState) => boolean;
  /** Products tab: split validate-time product_match_status filters. */
  showProductMatchStatusChips?: boolean;
  /** Optional counts for product no_match / ambiguous_eligible (tab-counts API; full job scope). */
  productMatchStatusCounts?: { no_match?: number; ambiguous_eligible?: number };
  /** Hide DSI-only provisional queue chip (e.g. CPOR has no provisional masters). */
  hideProvisionalQueue?: boolean;
  /** Hide verify-name / special-category / duplicate refine toggles when unused. */
  hideMatchToggles?: boolean;
}) {
  const resolveClearTarget = clearToDefault ?? defaultStewardCandidateFilterState;
  const filtersAreDefault = isAtDefault ?? stewardFiltersAreDefault;
  return (
    <Stack spacing={1} data-testid="dsi-steward-candidate-filters" role="region" aria-label="Filter mapping candidates">
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2" color="text.secondary">
          Filter candidates
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {totalCount === 0
              ? 'No open candidates on this tab'
              : `Showing ${visibleCount} of ${totalCount}`}
          </Typography>
          <Button
            size="small"
            variant="text"
            onClick={() => onChange(resolveClearTarget())}
            disabled={filtersAreDefault(filters)}
            data-testid="dsi-steward-filter-clear"
          >
            Clear filters
          </Button>
        </Stack>
      </Stack>
      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Plan / match
        </Typography>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          {(
            [
              ['all', 'All'],
              ['needs_review', 'Needs review'],
              ['ready_to_map', 'Ready to map'],
              ...(hideProvisionalQueue ? [] : ([['provisional', 'Provisional']] as const)),
              ['no_match', 'No match'],
              ...(showProductMatchStatusChips
                ? ([['ambiguous_eligible', 'Ambiguous']] as const)
                : []),
            ] as const
          ).map(([value, label]) => {
            const count =
              value === 'no_match'
                ? productMatchStatusCounts?.no_match
                : value === 'ambiguous_eligible'
                  ? productMatchStatusCounts?.ambiguous_eligible
                  : undefined;
            const chipLabel =
              count != null && (value === 'no_match' || value === 'ambiguous_eligible')
                ? `${label} (${count})`
                : label;
            return (
              <Chip
                key={value}
                size="small"
                label={chipLabel}
                variant={filters.queue === value ? 'filled' : 'outlined'}
                color={filters.queue === value ? 'primary' : 'default'}
                onClick={() => onChange({ ...filters, queue: value as StewardQueueFilter })}
                sx={{ cursor: 'pointer' }}
                data-testid={`dsi-filter-queue-${value}`}
              />
            );
          })}
        </Stack>
      </Stack>
      {hideEntityFilter ? null : (
        <Stack spacing={0.75}>
          <Typography variant="caption" color="text.secondary">
            Entity
          </Typography>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {(
              [
                ['all', 'All'],
                ['customer', 'Channel partner'],
                ['distributor', 'Distributor'],
                ['product', 'Product'],
              ] as const
            ).map(([value, label]) => (
              <Chip
                key={value}
                size="small"
                label={label}
                variant={filters.entity === value ? 'filled' : 'outlined'}
                color={filters.entity === value ? 'primary' : 'default'}
                onClick={() =>
                  onChange({
                    ...filters,
                    entity: value as StewardEntityFilter,
                    party: value === 'customer' || value === 'product' ? 'all' : filters.party,
                  })
                }
                sx={{ cursor: 'pointer' }}
                data-testid={`dsi-filter-entity-${value}`}
              />
            ))}
          </Stack>
        </Stack>
      )}
      {hidePartyFilter ? null : (
      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Party (distributor tokens only)
        </Typography>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          {(
            [
              ['all', 'All'],
              ['bill_to', 'Bill To'],
              ['ship_to', 'Ship To'],
            ] as const
          ).map(([value, label]) => (
            <Chip
              key={value}
              size="small"
              label={label}
              variant={filters.party === value ? 'filled' : 'outlined'}
              color={filters.party === value ? 'primary' : 'default'}
              onClick={() =>
                onChange({
                  ...filters,
                  party: value as StewardPartyFilter,
                  entity:
                    value !== 'all' && (filters.entity === 'customer' || filters.entity === 'product')
                      ? 'all'
                      : filters.entity,
                })
              }
              sx={{ cursor: 'pointer' }}
              data-testid={`dsi-filter-party-${value}`}
            />
          ))}
        </Stack>
      </Stack>
      )}
      {hideMatchToggles ? null : (
      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Refine (combine)
        </Typography>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Chip
            size="small"
            label="Verify name"
            variant={filters.verifyNameOnly ? 'filled' : 'outlined'}
            color={filters.verifyNameOnly ? 'warning' : 'default'}
            onClick={() => onChange({ ...filters, verifyNameOnly: !filters.verifyNameOnly })}
            sx={{ cursor: 'pointer' }}
            data-testid="dsi-filter-verify-name"
          />
          <Chip
            size="small"
            label="Special category"
            variant={filters.specialCategoryOnly ? 'filled' : 'outlined'}
            color={filters.specialCategoryOnly ? 'secondary' : 'default'}
            onClick={() => onChange({ ...filters, specialCategoryOnly: !filters.specialCategoryOnly })}
            sx={{ cursor: 'pointer' }}
            data-testid="dsi-filter-special-category"
          />
          <Chip
            size="small"
            label="Duplicate review needed"
            variant={filters.duplicateUnresolvedOnly ? 'filled' : 'outlined'}
            color={filters.duplicateUnresolvedOnly ? 'warning' : 'default'}
            onClick={() =>
              onChange({ ...filters, duplicateUnresolvedOnly: !filters.duplicateUnresolvedOnly })
            }
            sx={{ cursor: 'pointer' }}
            data-testid="dsi-filter-duplicate-unresolved"
          />
        </Stack>
      </Stack>
      )}
    </Stack>
  );
}

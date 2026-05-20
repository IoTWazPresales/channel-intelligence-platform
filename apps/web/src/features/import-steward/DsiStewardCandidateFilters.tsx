'use client';

import { Button, Chip, Stack, Typography } from '@mui/material';
import type { DsiStewardCandidateFilterState, DsiStewardEntityFilter, DsiStewardPartyFilter, DsiStewardQueueFilter } from './dsiStewardCandidateFilterLogic';
import { defaultDsiStewardCandidateFilterState, dsiStewardFiltersAreDefault } from './dsiStewardCandidateFilterLogic';

export function DsiStewardCandidateFilters({
  filters,
  onChange,
  visibleCount,
  totalCount,
  hideEntityFilter = false,
  hidePartyFilter = false,
}: {
  filters: DsiStewardCandidateFilterState;
  onChange: (next: DsiStewardCandidateFilterState) => void;
  visibleCount: number;
  totalCount: number;
  /** When true, entity is fixed by the active tab (tabbed resolution workspace). */
  hideEntityFilter?: boolean;
  /** Hide Bill To / Ship To when not on the Distributors tab. */
  hidePartyFilter?: boolean;
}) {
  /** Hide only when the tab/job has no open candidates at all — not when filters narrow to zero visible rows. */
  if (totalCount === 0) return null;

  return (
    <Stack spacing={1} data-testid="dsi-steward-candidate-filters" role="region" aria-label="Filter mapping candidates">
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2" color="text.secondary">
          Filter candidates
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Showing {visibleCount} of {totalCount}
          </Typography>
          <Button
            size="small"
            variant="text"
            onClick={() => onChange(defaultDsiStewardCandidateFilterState())}
            disabled={dsiStewardFiltersAreDefault(filters)}
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
              ['provisional', 'Provisional'],
              ['no_match', 'No match'],
            ] as const
          ).map(([value, label]) => (
            <Chip
              key={value}
              size="small"
              label={label}
              variant={filters.queue === value ? 'filled' : 'outlined'}
              color={filters.queue === value ? 'primary' : 'default'}
              onClick={() => onChange({ ...filters, queue: value as DsiStewardQueueFilter })}
              sx={{ cursor: 'pointer' }}
              data-testid={`dsi-filter-queue-${value}`}
            />
          ))}
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
                    entity: value as DsiStewardEntityFilter,
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
                  party: value as DsiStewardPartyFilter,
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
            label="Possible duplicates"
            variant={filters.possibleDuplicatesOnly ? 'filled' : 'outlined'}
            color={filters.possibleDuplicatesOnly ? 'info' : 'default'}
            onClick={() => onChange({ ...filters, possibleDuplicatesOnly: !filters.possibleDuplicatesOnly })}
            sx={{ cursor: 'pointer' }}
            data-testid="dsi-filter-possible-duplicates"
          />
        </Stack>
      </Stack>
    </Stack>
  );
}

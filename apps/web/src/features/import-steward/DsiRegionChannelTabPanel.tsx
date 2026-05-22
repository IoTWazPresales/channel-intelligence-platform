'use client';

import { Alert, Stack, Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';

import { safeDisplayError } from '@/lib/api';

import type { DsiCatalogOpt, DsiUnresolvedGeoRowDto } from './dsiSteward.types';
import { countUnresolvedGeoTokens } from './dsiUnresolvedGeoCount';
import { DsiChannelGeographicEvidenceSection } from './DsiChannelGeographicEvidenceSection';
import { UnresolvedGeoStewardPanel } from './UnresolvedGeoStewardPanel';

export function DsiRegionChannelTabPanel({
  importJobId,
  unresolvedGeoQuery,
  catalogChannels,
  catalogRegions,
  onInvalidate,
}: {
  importJobId: number;
  unresolvedGeoQuery: UseQueryResult<{
    import_job_id: number;
    channels: DsiUnresolvedGeoRowDto[];
    regions: DsiUnresolvedGeoRowDto[];
  }>;
  catalogChannels: DsiCatalogOpt[];
  catalogRegions: DsiCatalogOpt[];
  onInvalidate: () => void;
}) {
  const unresolvedCount = unresolvedGeoQuery.isSuccess
    ? countUnresolvedGeoTokens(unresolvedGeoQuery.data)
    : null;

  return (
    <Stack spacing={2} data-testid="dsi-region-channel-tab-panel" sx={{ py: 1 }}>
      <Typography variant="body2" color="text.secondary">
        File region and channel values that did not match the catalog. Map a synonym to an existing row, or create a
        governed catalog entry. Re-run import validation after changes so customer candidates pick up new aliases.
      </Typography>
      {unresolvedGeoQuery.fetchStatus === 'fetching' && !unresolvedGeoQuery.data ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-unresolved-geo-loading">
          Loading unresolved region and channel tokens…
        </Alert>
      ) : null}
      {unresolvedGeoQuery.isError ? (
        <Alert severity="error" data-testid="dsi-unresolved-geo-error">
          {safeDisplayError(unresolvedGeoQuery.error)}
        </Alert>
      ) : null}
      {unresolvedGeoQuery.isSuccess && unresolvedCount === 0 ? (
        <Alert severity="success" variant="outlined" data-testid="dsi-region-channel-all-resolved">
          All region and channel values from this import resolve to the catalog. Switch to Customers or Products to
          continue entity stewardship.
        </Alert>
      ) : null}
      {unresolvedGeoQuery.isSuccess ? (
        <DsiChannelGeographicEvidenceSection importJobId={importJobId} />
      ) : null}
      {unresolvedGeoQuery.isSuccess && unresolvedCount != null && unresolvedCount > 0 ? (
        <UnresolvedGeoStewardPanel
          importJobId={importJobId}
          channels={unresolvedGeoQuery.data?.channels ?? []}
          regions={unresolvedGeoQuery.data?.regions ?? []}
          catalogChannels={catalogChannels}
          catalogRegions={catalogRegions}
          onInvalidate={onInvalidate}
        />
      ) : null}
    </Stack>
  );
}

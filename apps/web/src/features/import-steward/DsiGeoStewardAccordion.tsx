'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Accordion, AccordionDetails, AccordionSummary, Alert, Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';

import { safeDisplayError } from '@/lib/api';

import type { DsiCatalogOpt, DsiUnresolvedGeoRowDto } from './dsiSteward.types';
import { UnresolvedGeoStewardPanel } from './UnresolvedGeoStewardPanel';

export function DsiGeoStewardAccordion({
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
  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{ my: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}
      data-testid="dsi-unresolved-geo-accordion"
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="body2" color="text.secondary">
          Route-to-market and region stewardship (unresolved file values)
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Alert severity="info" variant="outlined" sx={{ mb: 2 }} icon={false}>
          <Typography variant="caption" display="block">
            Create a governed catalog row when the source text is a genuine business category, or map with an alias when
            it is a true synonym. Leave unresolved if unclear — then use row overrides or fix the file.
          </Typography>
        </Alert>
        {unresolvedGeoQuery.fetchStatus === 'fetching' && !unresolvedGeoQuery.data ? (
          <Alert severity="info" variant="outlined" data-testid="dsi-unresolved-geo-loading">
            Loading unresolved route-to-market and region tokens…
          </Alert>
        ) : null}
        {unresolvedGeoQuery.isError ? (
          <Alert severity="error" data-testid="dsi-unresolved-geo-error">
            {safeDisplayError(unresolvedGeoQuery.error)}
          </Alert>
        ) : null}
        <UnresolvedGeoStewardPanel
          importJobId={importJobId}
          channels={unresolvedGeoQuery.data?.channels ?? []}
          regions={unresolvedGeoQuery.data?.regions ?? []}
          catalogChannels={catalogChannels}
          catalogRegions={catalogRegions}
          onInvalidate={onInvalidate}
        />
      </AccordionDetails>
    </Accordion>
  );
}

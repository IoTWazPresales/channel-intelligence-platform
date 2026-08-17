'use client';

import type { ReactNode } from 'react';
import { Chip, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import type {
  ImportStewardCandidateRowBase,
  ImportStewardWorkspaceColumn,
} from '@/features/import-steward/importStewardCandidateWorkspace.types';
import {
  INBOUND_STEWARD_ENTITY_CUST,
  INBOUND_STEWARD_ENTITY_DIST,
  inboundEvidenceContextNeedsNameReview,
  inboundEvidenceContextParty,
  inboundEvidenceContextPossibleDuplicateOf,
  inboundEvidenceContextSpecialCategory,
  inboundEvidenceEntityChipLabel,
  inboundEvidenceHumanizeMatchReasonCaption,
  inboundEvidenceHumanizeSnakeTitle,
  inboundEvidenceSampleToken,
  inboundEvidenceSuggestedNameFromContext,
} from './inboundEvidenceMappingCandidateDisplayUtils';

/** Row shape for inbound evidence mapping candidates (matches API + shipment steward). */
export type InboundEvidenceMappingCandidateRow = ImportStewardCandidateRowBase & {
  import_job_id: number;
  suggested_entity_id: number | null;
  suggested_action: string | null;
  suggested_distributor_code: string | null;
  suggested_distributor_name: string | null;
  suggested_customer_code: string | null;
  suggested_customer_name: string | null;
};

type CustomerHit = { id: number; customer_code: string; customer_name: string };

function CustomerMatchByIdEmbedded({ id }: { id: number }) {
  const { data, isPending } = useQuery({
    queryKey: ['customers-list-by-id-shipment-steward', id],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(`/api/v1/customers?customer_id=${id}&page_size=1`, { signal }),
    enabled: Number.isFinite(id) && id > 0,
  });
  const hit = data?.items?.[0];
  if (isPending) {
    return (
      <Typography variant="caption" color="text.secondary">
        Loading…
      </Typography>
    );
  }
  if (!hit) {
    return (
      <Stack spacing={0.25}>
        <Typography variant="body2">Matched customer</Typography>
        <Typography variant="caption" color="text.secondary">
          ID {id}
        </Typography>
      </Stack>
    );
  }
  return (
    <Stack spacing={0.25}>
      <Typography variant="body2">{hit.customer_name || '—'}</Typography>
      <Typography variant="caption" color="text.secondary">
        {(hit.customer_code || '').trim() || '—'}
      </Typography>
    </Stack>
  );
}

function inboundEvidenceActionChipColor(a: string | null) {
  switch (a) {
    case 'map_distributor':
    case 'map_customer':
      return 'success' as const;
    case 'create_provisional_distributor':
    case 'create_provisional_customer':
      return 'warning' as const;
    case 'needs_review':
      return 'error' as const;
    default:
      return 'default' as const;
  }
}

function InboundEvidenceMatchCell({ row }: { row: InboundEvidenceMappingCandidateRow }) {
  const mr = (row.match_reason || '').trim();
  const act = (row.suggested_action || '').trim();
  const sid = row.suggested_entity_id;
  const needsReview =
    act === 'needs_review' || ((!act || act === '') && (row.status || '').trim() === 'needs_review');

  if (row.entity_type === INBOUND_STEWARD_ENTITY_DIST) {
    if (!row.match_reason) {
      return (
        <Typography variant="caption" color="text.secondary">
          —
        </Typography>
      );
    }
    return (
      <Typography variant="caption" color="text.secondary">
        {inboundEvidenceHumanizeSnakeTitle(mr)}
      </Typography>
    );
  }

  if (act === 'map_customer' && sid != null && Number(sid) > 0) {
    const hasName =
      Boolean((row.suggested_customer_name || '').trim()) || Boolean((row.suggested_customer_code || '').trim());
    if (hasName) {
      return (
        <Stack spacing={0.25}>
          <Typography variant="body2">{(row.suggested_customer_name || '').trim() || '—'}</Typography>
          <Typography variant="caption" color="text.secondary">
            {(row.suggested_customer_code || '').trim() || '—'}
          </Typography>
        </Stack>
      );
    }
    return <CustomerMatchByIdEmbedded id={Number(sid)} />;
  }

  if (needsReview) {
    const cap = inboundEvidenceHumanizeMatchReasonCaption(row.match_reason);
    return (
      <Stack spacing={0.25}>
        <Typography variant="body2">Needs review</Typography>
        {cap ? (
          <Typography variant="caption" color="text.secondary">
            {cap}
          </Typography>
        ) : null}
      </Stack>
    );
  }

  if (mr === 'no_alias_or_exact_dim_match') {
    return (
      <Typography variant="body2" color="text.secondary">
        No match found
      </Typography>
    );
  }

  return (
    <Typography variant="caption" color="text.secondary">
      {inboundEvidenceHumanizeSnakeTitle(row.match_reason)}
    </Typography>
  );
}

export type InboundEvidenceMappingCandidateWorkspaceColumnOptions = {
  renderActionsCell?: (row: InboundEvidenceMappingCandidateRow) => ReactNode;
};

/**
 * Default column set aligned with `ShipmentEntityStewardPanel` list (actions supplied separately).
 */
export function buildInboundEvidenceMappingCandidateWorkspaceColumns(
  opts?: InboundEvidenceMappingCandidateWorkspaceColumnOptions
): ImportStewardWorkspaceColumn<InboundEvidenceMappingCandidateRow>[] {
  const cols: ImportStewardWorkspaceColumn<InboundEvidenceMappingCandidateRow>[] = [
    {
      id: 'type',
      header: 'Type',
      cell: (r) => <Chip size="small" label={inboundEvidenceEntityChipLabel(r.entity_type)} variant="outlined" />,
    },
    {
      id: 'party',
      header: 'Party / scope',
      cell: (r) => (
        <Typography variant="body2">
          {r.entity_type === INBOUND_STEWARD_ENTITY_DIST ? inboundEvidenceContextParty(r.context) : '—'}
        </Typography>
      ),
    },
    {
      id: 'token',
      header: 'Token (sample)',
      cellSx: { maxWidth: 260 },
      cell: (r) => {
        const tok = inboundEvidenceSampleToken(r.sample_raw_values, r.normalized_key);
        return (
          <>
            <Typography variant="body2" noWrap title={tok}>
              {tok}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" noWrap title={r.normalized_key}>
              key: {r.normalized_key}
            </Typography>
          </>
        );
      },
    },
    {
      id: 'rows',
      header: 'Rows',
      align: 'right',
      cell: (r) => r.row_count,
    },
    {
      id: 'qty_value',
      header: 'Qty / value',
      align: 'right',
      cell: (r) => (
        <Typography variant="caption" display="block">
          {r.total_units ?? '—'} / {r.total_reported_value ?? '—'}
        </Typography>
      ),
    },
    {
      id: 'suggested',
      header: 'Suggested',
      cell: (r) => {
        const tok = inboundEvidenceSampleToken(r.sample_raw_values, r.normalized_key);
        return (
          <Stack spacing={0.5} alignItems="flex-start">
            <Typography variant="body2">{inboundEvidenceSuggestedNameFromContext(r.context, tok)}</Typography>
            {r.entity_type === INBOUND_STEWARD_ENTITY_CUST && inboundEvidenceContextSpecialCategory(r.context) === 'noise_only' ? (
              <Chip size="small" color="secondary" variant="outlined" label="Special category" />
            ) : null}
            {r.entity_type === INBOUND_STEWARD_ENTITY_CUST && inboundEvidenceContextSpecialCategory(r.context) === 'internal_note' ? (
              <Chip size="small" color="info" variant="outlined" label="Internal note" />
            ) : null}
            {r.entity_type === INBOUND_STEWARD_ENTITY_CUST && inboundEvidenceContextPossibleDuplicateOf(r.context).length > 0 ? (
              <Typography variant="caption" color="text.secondary">
                Similar to: {inboundEvidenceContextPossibleDuplicateOf(r.context).join(', ')}
              </Typography>
            ) : null}
            {r.entity_type === INBOUND_STEWARD_ENTITY_CUST && inboundEvidenceContextNeedsNameReview(r.context) ? (
              <Chip size="small" color="warning" variant="outlined" label="Verify name" />
            ) : null}
            {r.entity_type === INBOUND_STEWARD_ENTITY_DIST && (r.suggested_distributor_code || r.suggested_distributor_name) ? (
              <Typography variant="caption" color="text.secondary">
                {(r.suggested_distributor_code || '').trim()}
                {r.suggested_distributor_name ? ` — ${r.suggested_distributor_name}` : ''}
              </Typography>
            ) : null}
            {r.entity_type === INBOUND_STEWARD_ENTITY_CUST && (r.suggested_customer_code || r.suggested_customer_name) ? (
              <Typography variant="caption" color="text.secondary">
                {(r.suggested_customer_code || '').trim()}
                {r.suggested_customer_name ? ` — ${r.suggested_customer_name}` : ''}
              </Typography>
            ) : null}
          </Stack>
        );
      },
    },
    {
      id: 'plan',
      header: 'Plan',
      cell: (r) => (
        <Stack spacing={0.5} alignItems="flex-start">
          {r.suggested_action ? (
            <Chip size="small" label={r.suggested_action} color={inboundEvidenceActionChipColor(r.suggested_action)} />
          ) : null}
          {r.confidence_score != null ? (
            <Typography variant="caption" color="text.secondary">
              score {r.confidence_score.toFixed(2)}
            </Typography>
          ) : null}
        </Stack>
      ),
    },
    {
      id: 'match',
      header: 'Match',
      cellSx: { maxWidth: 220 },
      cell: (r) => <InboundEvidenceMatchCell row={r} />,
    },
  ];

  if (opts?.renderActionsCell) {
    cols.push({
      id: 'actions',
      header: 'Actions',
      align: 'right',
      cell: (r) => opts.renderActionsCell!(r),
    });
  }

  return cols;
}

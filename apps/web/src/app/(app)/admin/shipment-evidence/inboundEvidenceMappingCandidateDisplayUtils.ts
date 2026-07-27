/**
 * Shipment steward display helpers. Generic context parsers live in
 * `@/features/import-steward/stewardEvidenceContextDisplayUtils`.
 */

import {
  stewardEvidenceContextNeedsNameReview,
  stewardEvidenceContextParty,
  stewardEvidenceContextPossibleDuplicateOf,
  stewardEvidenceContextSpecialCategory,
  stewardEvidenceHumanizeMatchReasonCaption,
  stewardEvidenceHumanizeSnakeTitle,
  stewardEvidencePartyLabel,
  stewardEvidenceSampleToken,
  stewardEvidenceSuggestedNameFromContext,
} from '@/features/import-steward/stewardEvidenceContextDisplayUtils';

/**
 * Entity type strings aligned with shipment steward filters.
 * API entity_type literals contain "shipment_" (contract values).
 */
export const INBOUND_STEWARD_ENTITY_DIST = 'shipment_distributor' as const;
export const INBOUND_STEWARD_ENTITY_CUST = 'shipment_customer_token' as const;

/** Bill To / Ship To label — matches shipment steward semantics. */
export const inboundEvidencePartyLabel = stewardEvidencePartyLabel;

export const inboundEvidenceContextParty = stewardEvidenceContextParty;

export const inboundEvidenceSampleToken = stewardEvidenceSampleToken;

export const inboundEvidenceSuggestedNameFromContext = stewardEvidenceSuggestedNameFromContext;

export const inboundEvidenceContextNeedsNameReview = stewardEvidenceContextNeedsNameReview;

export const inboundEvidenceContextSpecialCategory = stewardEvidenceContextSpecialCategory;

export const inboundEvidenceContextPossibleDuplicateOf = stewardEvidenceContextPossibleDuplicateOf;

export function inboundEvidenceEntityChipLabel(entityType: string): string {
  const et = (entityType || '').trim();
  if (
    et === INBOUND_STEWARD_ENTITY_DIST ||
    et === 'distributor_token' ||
    et === 'shipment_distributor'
  ) {
    return 'Distributor';
  }
  if (
    et === INBOUND_STEWARD_ENTITY_CUST ||
    et === 'customer_dealer_token' ||
    et === 'shipment_customer_token'
  ) {
    return 'Channel partner';
  }
  return entityType;
}

export const inboundEvidenceHumanizeSnakeTitle = stewardEvidenceHumanizeSnakeTitle;

export const inboundEvidenceHumanizeMatchReasonCaption = stewardEvidenceHumanizeMatchReasonCaption;

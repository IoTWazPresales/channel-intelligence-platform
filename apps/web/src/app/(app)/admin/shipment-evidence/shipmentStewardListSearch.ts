import type { ShipmentMappingCandidateRow } from './shipmentMappingCandidateDisplay';
import { inboundEvidenceSampleToken } from './inboundEvidenceMappingCandidateDisplayUtils';

/** Client-side list search (S3) — debounced query applied after queue/chip filters. */
export function filterShipmentStewardRowsBySearch<T extends ShipmentMappingCandidateRow>(
  rows: T[],
  search: string
): T[] {
  const needle = search.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((r) => {
    const token = inboundEvidenceSampleToken(r.sample_raw_values, r.normalized_key).toLowerCase();
    const key = (r.normalized_key || '').toLowerCase();
    const status = (r.status || '').toLowerCase();
    const matchReason = (r.match_reason || '').toLowerCase();
    const suggestedAction = (r.suggested_action || '').toLowerCase();
    const distCode = (r.suggested_distributor_code || '').toLowerCase();
    const distName = (r.suggested_distributor_name || '').toLowerCase();
    const custCode = (r.suggested_customer_code || '').toLowerCase();
    const custName = (r.suggested_customer_name || '').toLowerCase();
    return (
      token.includes(needle) ||
      key.includes(needle) ||
      status.includes(needle) ||
      matchReason.includes(needle) ||
      suggestedAction.includes(needle) ||
      distCode.includes(needle) ||
      distName.includes(needle) ||
      custCode.includes(needle) ||
      custName.includes(needle) ||
      String(r.row_count).includes(needle) ||
      (r.sample_raw_values ?? []).some((v) => String(v).toLowerCase().includes(needle))
    );
  });
}

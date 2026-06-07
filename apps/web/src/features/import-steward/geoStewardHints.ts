/** Client helpers for geo steward row classification (mirrors API geographic_hint when stale). */

import type { DsiUnresolvedGeoRowDto } from './dsiSteward.types';

/** True when the file token looks geographic — region alias is the primary steward path. */
export function geoRowHasRegionHint(row: DsiUnresolvedGeoRowDto): boolean {
  return Boolean(row.geographic_hint?.guessed_region_code);
}

export function geoRowIsoHint(row: DsiUnresolvedGeoRowDto): string | null {
  const code = row.geographic_hint?.guessed_region_code;
  return code && String(code).trim() ? String(code).trim().toUpperCase() : null;
}

/** True when steward already saved a region_source_token_alias for this geographic channel token. */
export function geoRowRegionAliasRegistered(row: DsiUnresolvedGeoRowDto): boolean {
  return Boolean(row.geographic_hint?.alias_registered);
}

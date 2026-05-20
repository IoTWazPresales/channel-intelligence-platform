import type { DsiUnresolvedGeoRowDto } from './dsiSteward.types';

export function countUnresolvedGeoTokens(data: {
  channels?: DsiUnresolvedGeoRowDto[];
  regions?: DsiUnresolvedGeoRowDto[];
} | null | undefined): number {
  if (!data) return 0;
  return (data.channels?.length ?? 0) + (data.regions?.length ?? 0);
}

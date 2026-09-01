/** Stock container lens keys — buyer-facing labels per CIP_DESIGN_LANGUAGE v1.1 §5. */
export const STOCK_LENSES = [
  { id: 'movement', label: 'Sell-out' },
  { id: 'execution', label: 'Fill vs plan' },
  { id: 'cover', label: 'Cover' },
  { id: 'inbound', label: 'Inbound' },
] as const;

export type StockLensId = (typeof STOCK_LENSES)[number]['id'];

export const DEFAULT_STOCK_LENS: StockLensId = 'movement';

export function parseStockLens(raw: string | null | undefined): StockLensId {
  const v = (raw || '').trim().toLowerCase();
  if (STOCK_LENSES.some((l) => l.id === v)) return v as StockLensId;
  return DEFAULT_STOCK_LENS;
}

export function stockLensLabel(lens: StockLensId): string {
  return STOCK_LENSES.find((l) => l.id === lens)?.label ?? lens;
}

/** WoC histogram buckets aligned to stock-cover.html mockup. */
export type WocBucketId = 'lt2' | '2to4' | '4to8' | '8to13' | 'gte13';

export const WOC_BUCKET_LABELS: Record<WocBucketId, string> = {
  lt2: '<2w',
  '2to4': '2–4w',
  '4to8': '4–8w',
  '8to13': '8–13w',
  gte13: '13w+',
};

export function wocBucket(weeks: number | null | undefined): WocBucketId | null {
  if (weeks == null || Number.isNaN(weeks)) return null;
  if (weeks < 2) return 'lt2';
  if (weeks < 4) return '2to4';
  if (weeks < 8) return '4to8';
  if (weeks < 13) return '8to13';
  return 'gte13';
}

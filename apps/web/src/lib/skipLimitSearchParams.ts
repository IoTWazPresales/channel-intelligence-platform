/** Parse skip/limit list pagination from URL search params (shipping / shipment-evidence dialect). */
export function parseSkipLimitParams(
  sp: URLSearchParams,
  options: { defaultLimit: number; pageSizeOptions: readonly number[] },
): { skip: number; limit: number } {
  const skip = Math.max(0, Number(sp.get('skip') || '0') || 0);
  const limitRaw = Number(sp.get('limit') || String(options.defaultLimit)) || options.defaultLimit;
  const limit = options.pageSizeOptions.includes(limitRaw) ? limitRaw : options.defaultLimit;
  return { skip, limit };
}

/** 1-based page from skip/limit (MasterDataGridShell dialect). */
export function pageFromSkipLimit(skip: number, limit: number): number {
  if (limit <= 0) return 1;
  return Math.floor(Math.max(0, skip) / limit) + 1;
}

/** skip offset from 1-based page. */
export function skipFromPage(page: number, limit: number): number {
  const p = Math.max(1, Math.floor(page) || 1);
  const lim = Math.max(1, Math.floor(limit) || 1);
  return (p - 1) * lim;
}

/** 0-based page index from offset/limit (PVE exc_offset dialect). */
export function zeroBasedPageFromOffset(offset: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.floor(Math.max(0, offset) / limit);
}

/** offset from 0-based page index. */
export function offsetFromZeroBasedPage(page: number, limit: number): number {
  const p = Math.max(0, Math.floor(page) || 0);
  const lim = Math.max(1, Math.floor(limit) || 1);
  return p * lim;
}

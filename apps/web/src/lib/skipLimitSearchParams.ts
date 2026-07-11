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

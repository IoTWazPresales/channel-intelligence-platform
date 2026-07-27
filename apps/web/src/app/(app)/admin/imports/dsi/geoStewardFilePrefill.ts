/** Client-side prefill for geo steward "register from file" (mirrors ``suggest_geo_create_prefill_sync``). */

export function prefillGeoCreateFromFileToken(
  rawToken: string,
  normalizedToken: string,
  dimension: 'channel' | 'region'
): { code: string; name: string } {
  const rt = rawToken.trim();
  const nk = (normalizedToken || rt).trim();
  if (dimension === 'region') {
    const code = nk.toUpperCase().replace(/\s+/g, '_').slice(0, 32);
    const name = titleFromNormalized(nk, rt);
    return { code, name };
  }
  const code = nk.toUpperCase().replace(/\s+/g, '_').slice(0, 32);
  const name = titleFromNormalized(nk, rt);
  return { code, name };
}

function titleFromNormalized(normalized: string, fallback: string): string {
  if (!normalized) return fallback.slice(0, 256);
  return normalized
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .slice(0, 256);
}

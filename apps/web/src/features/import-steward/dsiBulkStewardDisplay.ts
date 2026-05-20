export function bulkPreviewProposedLabel(r: Record<string, unknown>): string {
  const x = r.proposed_display_name;
  if (typeof x === 'string' && x.trim()) return x.trim();
  return '';
}

export function bulkPreviewAliasEvidence(r: Record<string, unknown>): string {
  const ev =
    r.source_customer_alias_evidence ??
    r.source_customer_alias_raw_preview ??
    r.alias_raw_preview ??
    r.normalized_token_preview;
  if (typeof ev === 'string' && ev.trim()) return ev.trim();
  return '';
}

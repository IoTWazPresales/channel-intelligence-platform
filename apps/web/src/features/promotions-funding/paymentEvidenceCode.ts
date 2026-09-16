export function parseExactPaymentEvidenceCode(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const trimmed = raw.trim();
  return trimmed === '' ? null : trimmed;
}

export function isExactCaseCode(value: string | null | undefined, code: string): boolean {
  return value === code;
}

export function filterTokensByExactCaseCode<T extends { token: string }>(items: T[], code: string): T[] {
  return items.filter((item) => item.token === code);
}

/** Legal names stored in capitals become a display name. Mixed-case names are left as stored. */
const KEEP_UPPER = new Set(['pty', 'ltd', 'cc', 'inc', 'llc', 'plc']);

export function displayPartyName(raw: string): string {
  const letters = raw.replace(/[^A-Za-z]/g, '');
  if (letters.length < 4 || letters !== letters.toUpperCase()) return raw;
  return raw.replace(/[A-Za-z][A-Za-z']*/g, (word) => {
    const lower = word.toLowerCase();
    if (KEEP_UPPER.has(lower)) return word.toUpperCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  });
}

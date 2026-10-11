/** Next calendar quarter for lineup authoring. UTC so the label does not shift with the browser zone. */

export function nextLineupQuarter(now: Date = new Date()): {
  periodStart: string;
  periodLabel: string;
} {
  const month = now.getUTCMonth();
  const year = now.getUTCFullYear();
  const currentQ = Math.floor(month / 3) + 1;
  const rolls = currentQ === 4;
  const nextQ = rolls ? 1 : currentQ + 1;
  const nextYear = rolls ? year + 1 : year;
  const startMonth = String((nextQ - 1) * 3 + 1).padStart(2, '0');
  return {
    periodStart: `${nextYear}-${startMonth}-01`,
    periodLabel: `${nextYear}Q${nextQ}`,
  };
}

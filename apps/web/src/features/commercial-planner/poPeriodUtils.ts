/** Calendar quarter label matching lineup period filters (e.g. `26Q2`). */
export function currentQuarterLabel(d = new Date()): string {
  const q = Math.floor(d.getMonth() / 3) + 1;
  const yy = String(d.getFullYear()).slice(-2);
  return `${yy}Q${q}`;
}

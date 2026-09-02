import { distributors, products } from './entities';

export type CoverRow = {
  id: string;
  distributorId: number;
  distributor: string;
  productId: number;
  sku: string;
  product: string;
  family: string;
  soh: number;
  weeklyRate: number;
  weeksOfCover: number;
  inboundOpen: number;
  vintageDays: number;
  status: 'breach' | 'watch' | 'ok' | 'excess';
};

/** Deterministic pseudo-random so renders are stable between runs. */
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

const rnd = seeded(2026);

export const coverRows: CoverRow[] = distributors.flatMap((d) =>
  products.map((p) => {
    const weeklyRate = Math.max(2, Math.round(rnd() * 140));
    const soh = Math.round(weeklyRate * (0.6 + rnd() * 9));
    const woc = weeklyRate ? soh / weeklyRate : 0;
    const status: CoverRow['status'] = woc < 2 ? 'breach' : woc < 4 ? 'watch' : woc > 8 ? 'excess' : 'ok';
    return {
      id: `${d.id}-${p.id}`,
      distributorId: d.id,
      distributor: d.name,
      productId: p.id,
      sku: p.sku,
      product: p.name,
      family: p.family,
      soh,
      weeklyRate,
      weeksOfCover: Math.round(woc * 10) / 10,
      inboundOpen: rnd() > 0.55 ? Math.round(rnd() * 400) : 0,
      vintageDays: Math.round(rnd() * 21),
      status,
    };
  })
);

export const coverSummary = (() => {
  const breach = coverRows.filter((r) => r.status === 'breach').length;
  const watch = coverRows.filter((r) => r.status === 'watch').length;
  const excess = coverRows.filter((r) => r.status === 'excess').length;
  const soh = coverRows.reduce((a, r) => a + r.soh, 0);
  const rate = coverRows.reduce((a, r) => a + r.weeklyRate, 0);
  return { pairs: coverRows.length, breach, watch, excess, soh, weeklyRate: rate, networkCover: Math.round((soh / rate) * 10) / 10 };
})();

export const coverDistribution = [
  { bucket: '<1w', pairs: coverRows.filter((r) => r.weeksOfCover < 1).length },
  { bucket: '1–2w', pairs: coverRows.filter((r) => r.weeksOfCover >= 1 && r.weeksOfCover < 2).length },
  { bucket: '2–4w', pairs: coverRows.filter((r) => r.weeksOfCover >= 2 && r.weeksOfCover < 4).length },
  { bucket: '4–6w', pairs: coverRows.filter((r) => r.weeksOfCover >= 4 && r.weeksOfCover < 6).length },
  { bucket: '6–8w', pairs: coverRows.filter((r) => r.weeksOfCover >= 6 && r.weeksOfCover < 8).length },
  { bucket: '8w+', pairs: coverRows.filter((r) => r.weeksOfCover >= 8).length },
];

export type WeekPoint = { week: string; sellOut: number; shipped: number; soh: number };

export const weeklySeries: WeekPoint[] = (() => {
  const r = seeded(77);
  let soh = 21_400;
  const out: WeekPoint[] = [];
  for (let i = 24; i <= 36; i++) {
    const sellOut = 2_300 + Math.round(r() * 900) + (i > 31 ? 350 : 0);
    const shipped = 2_000 + Math.round(r() * 1_400);
    soh = Math.max(9_000, soh + shipped - sellOut);
    out.push({ week: `W${i}`, sellOut, shipped, soh });
  }
  return out;
})();

export const sellOutByFamily = [
  { family: 'Monitors', units: 12_840, share: 0.46, wow: 0.04 },
  { family: 'Notebooks', units: 9_120, share: 0.33, wow: -0.02 },
  { family: 'Accessories', units: 4_330, share: 0.16, wow: 0.11 },
  { family: 'Print', units: 1_410, share: 0.05, wow: -0.06 },
];

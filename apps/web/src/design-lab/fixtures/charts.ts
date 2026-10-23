/**
 * Chart grammar fixtures (N-0114). Deterministic: no randomness, no dates from the clock, so
 * screenshots at 1280x800 and 390x844 stay stable. Every name is fictional.
 */

/** 37 customers, names 6 to 62 characters, in no particular order (sorting is the chart's job). */
const CUSTOMER_NAMES = [
  'Northern Cape Consolidated Retail Holdings (Pty) Ltd Kimberley',
  'Blue Crane Outfitters',
  'Kuruman',
  'Highveld Home and Office Electronics Wholesale Co-operative',
  'Umlazi Corner Store',
  'Sandveld Agricultural Supply Group',
  'Mopane Traders',
  'Garden Route Digital and Appliance Centres (Mossel Bay Branch)',
  'Lowveld Value Stores',
  'Bushveld Bargains',
  'Coastal Technology Supply Partners',
  'Overberg',
  'Drakensberg Mountain Retail',
  'Wild Coast General Dealer Network',
  'Namakwa Online',
  'Free State Farmers Hardware and Electrical Co-op Limited',
  'Kalahari Gadgets',
  'Waterberg Office Depot',
  'Midlands Meander Merchants',
  'Cape Flats Family Electronics',
  'Tsitsikamma Trading Post',
  'Breede Valley Wholesale',
  'Zululand Rural Retail Alliance (Ulundi, Nongoma and Vryheid)',
  'Soutpansberg Supplies',
  'Hantam Home',
  'West Coast Way Stores',
  'Magaliesberg Mega Mart',
  'Little Karoo Lifestyle & Electronics',
  'Pondoland Provisions',
  'Cederberg Corner',
  'Eastern Cape Independent Retailers Buying Association',
  'Swartland Stores',
  'Richtersveld',
  'Klein Karoo Kooperasie',
  'Limpopo Valley Electronics Emporium',
  'Vaal Triangle Value Warehouse',
  'Agulhas Plain Appliances',
];

/** Values from 18 400 000 down to 4 200 on a steep curve, then interleaved by a fixed step. */
export const longCustomers = CUSTOMER_NAMES.map((name, i) => {
  const rank = (i * 11) % CUSTOMER_NAMES.length;
  const value = Math.round(4_200 + (18_400_000 - 4_200) * ((CUSTOMER_NAMES.length - 1 - rank) / (CUSTOMER_NAMES.length - 1)) ** 4);
  return { customer: name, value };
});

export const fewShort = [
  { channel: 'Retail', count: 412 },
  { channel: 'Online', count: 288 },
  { channel: 'Dealer', count: 156 },
  { channel: 'Export', count: 41 },
  { channel: 'Staff', count: 12 },
  { channel: 'Other', count: 7 },
];

/** Seven labels of 15 to 24 characters, drawn vertical on purpose to show the two-line wrap. */
export const verticalWrap = [
  { family: 'Gaming notebooks', units: 1_840 },
  { family: 'Business notebooks 14in', units: 2_310 },
  { family: 'Creator desktops', units: 640 },
  { family: 'All-in-one desktops', units: 905 },
  { family: 'Curved gaming monitors', units: 1_220 },
  { family: 'Wireless mice and pads', units: 3_480 },
  { family: 'Mechanical keyboards', units: 2_050 },
];

/** 26 weeks: shipped in (bar), sell-out (line), stock on hand (area). */
export const weeks26 = Array.from({ length: 26 }, (_, i) => {
  const week = `2026-W${String(i + 14).padStart(2, '0')}`;
  const sellOut = 4_200 + Math.round(900 * Math.sin(i / 3)) + i * 40;
  const shipped = i % 4 === 0 ? 9_800 : i % 4 === 2 ? 3_100 : 0;
  const soh = 26_000 - i * 260 + Math.round(1_400 * Math.cos(i / 4));
  return { week, shipped, sellOut, soh };
});

export const pairedCustomers = CUSTOMER_NAMES.slice(0, 12).map((customer, i) => {
  const plan = 2_000 + ((i * 7) % 12) * 650;
  const shipped = Math.round(plan * (0.55 + ((i * 5) % 9) * 0.07));
  return { customer, plan, shipped };
});

export const pairedQuarters = ['25Q3', '25Q4', '26Q1', '26Q2', '26Q3', '26Q4*'].map((label, i) => ({
  label,
  ly: 41_000 + i * 2_600,
  cur: i === 5 ? 18_400 : 44_500 + i * 3_100,
}));

export const pieSlices = [
  { label: 'Northern Cape Consolidated Retail Holdings (Pty) Ltd — Kimberley', value: 412_000 },
  { label: 'Garden Route Digital and Appliance Centres (Mossel Bay Branch)', value: 288_500 },
  { label: 'Highveld Home and Office Electronics Wholesale Co-operative', value: 176_250 },
  { label: 'Coastal Technology Supply Partners', value: 121_000 },
  { label: 'Blue Crane Outfitters', value: 64_800 },
  { label: 'Midlands Meander Merchants', value: 41_900 },
  { label: 'Karoo', value: 22_300 },
  { label: 'Swartland Stores', value: 9_750 },
  { label: 'Richtersveld', value: 3_100 },
];

/** One small series per unit kind. */
export const unitSeries = {
  zar: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, v: 1_150_000 + i * 86_000 + (i % 3) * 140_000 })),
  usd: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, v: 38_000 + i * 2_400 - (i % 4) * 3_100 })),
  units: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, v: 7_400 + i * 380 + (i % 2) * 900 })),
  percent: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, v: Math.round((0.42 + i * 0.05 - (i % 3) * 0.02) * 1000) / 1000 })),
  count: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, v: 120 + i * 9 + (i % 5) * 4 })),
};

export const coverWeeks = [
  { label: 'Highveld Home and Office Electronics Wholesale', value: 6.4 },
  { label: 'Coastal Technology Supply Partners', value: 3.6 },
  { label: 'Kwazulu Channel Partners', value: 1.8 },
  { label: 'Karoo', value: 9.2 },
  { label: 'Overberg', value: 4.1 },
  { label: 'Namakwa Online', value: 0.6 },
];

export const podDays = [
  { label: 'Arrived, no proof of delivery', value: 23 },
  { label: 'Landed this week', value: 2 },
  { label: 'Overdue against promise', value: 41 },
  { label: 'In the pipeline', value: 12 },
];

/** 52 weeks of sell-out, one series. */
export const weeks52 = Array.from({ length: 52 }, (_, i) => ({
  week: `W${String(i + 1).padStart(2, '0')}`,
  sellOut: 5_600 + Math.round(1_800 * Math.sin(i / 5)) + Math.round(i * 22),
}));

export const oneCategory = [{ customer: 'Blue Crane Outfitters', value: 18_250 }];

export const allNulls = [
  { customer: 'Karoo', value: null },
  { customer: 'Overberg', value: null },
  { customer: 'Richtersveld', value: null },
];

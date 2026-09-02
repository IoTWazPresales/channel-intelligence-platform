/**
 * Design-lab fixture data. Fictional distributors, retailers and products with figures that the
 * real CIP data layer can derive (SOH, weeks of cover, sell-out, plan vs shipped, funding book).
 * Nothing here is read from or written to the API.
 */

export type Distributor = { id: number; code: string; name: string; region: string };
export type Customer = { id: number; code: string; name: string; group: string; strategic: boolean };
export type Product = { id: number; sku: string; name: string; family: string; active: boolean };

export const distributors: Distributor[] = [
  { id: 9, code: 'MER', name: 'Meridian Distribution', region: 'Gauteng' },
  { id: 12, code: 'CTS', name: 'Coastal Tech Supply', region: 'Western Cape' },
  { id: 15, code: 'HVW', name: 'Highveld Wholesale', region: 'Gauteng' },
  { id: 18, code: 'KZC', name: 'Kwazulu Channel Partners', region: 'KwaZulu-Natal' },
];

export const customers: Customer[] = [
  { id: 101, code: 'TMT', name: 'TechMart', group: 'TechMart Group', strategic: true },
  { id: 102, code: 'MEL', name: 'Metro Electronics', group: 'Metro Retail', strategic: true },
  { id: 103, code: 'HFH', name: 'HiFi House', group: 'Independent', strategic: false },
  { id: 104, code: 'OFW', name: 'OfficeWorld', group: 'OfficeWorld', strategic: true },
  { id: 105, code: 'GZN', name: 'Game Zone', group: 'Metro Retail', strategic: false },
  { id: 106, code: 'BYT', name: 'Byte & Co', group: 'Independent', strategic: false },
  { id: 107, code: 'OPEN', name: 'Open channel', group: 'Open channel', strategic: false },
];

export const products: Product[] = [
  { id: 61, sku: 'UX2780Q', name: '27" QHD IPS Monitor UX2780Q', family: 'Monitors', active: true },
  { id: 62, sku: 'UX3440W', name: '34" UWQHD Curved UX3440W', family: 'Monitors', active: true },
  { id: 63, sku: 'UX2410F', name: '24" FHD Office UX2410F', family: 'Monitors', active: true },
  { id: 71, sku: 'NBP14-I7', name: 'Notebook Pro 14 i7 / 16GB / 512', family: 'Notebooks', active: true },
  { id: 72, sku: 'NBP16-I9', name: 'Notebook Pro 16 i9 / 32GB / 1TB', family: 'Notebooks', active: true },
  { id: 73, sku: 'NBE15-I5', name: 'Notebook Essential 15 i5 / 8GB', family: 'Notebooks', active: true },
  { id: 81, sku: 'DK-TB4', name: 'Thunderbolt 4 Dock DK-TB4', family: 'Accessories', active: true },
  { id: 82, sku: 'KB-MX', name: 'Mechanical Keyboard KB-MX', family: 'Accessories', active: true },
  { id: 83, sku: 'WC-4K', name: '4K Webcam WC-4K', family: 'Accessories', active: false },
  { id: 91, sku: 'PR-L2600', name: 'Laser Printer PR-L2600', family: 'Print', active: true },
];

export const tenant = { name: 'Aurora Displays SA', period: 'FY26 P09 · W36', currency: 'R' };

export function fmtCurrency(v: number, opts: { compact?: boolean } = {}): string {
  if (opts.compact) {
    if (Math.abs(v) >= 1_000_000) return `${tenant.currency}${(v / 1_000_000).toFixed(1)}m`;
    if (Math.abs(v) >= 1_000) return `${tenant.currency}${Math.round(v / 1_000)}k`;
  }
  return `${tenant.currency}${Math.round(v).toLocaleString('en-ZA')}`;
}

export function fmtInt(v: number): string {
  return Math.round(v).toLocaleString('en-ZA');
}

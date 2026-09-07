export type SupplyLens = 'hub' | 'shipments' | 'receipts' | 'po';

export const SUPPLY_LEAVES: { value: Exclude<SupplyLens, 'hub'>; label: string; href: string }[] = [
  { value: 'shipments', label: 'Shipments', href: '/supply/shipments' },
  { value: 'receipts', label: 'Receipts & POD', href: '/admin/shipment-evidence' },
  { value: 'po', label: 'PO coverage', href: '/admin/po-management' },
];

export function supplyLensFromPath(pathname: string): SupplyLens {
  if (pathname.startsWith('/supply/shipments')) return 'shipments';
  if (pathname.startsWith('/admin/shipment-evidence')) return 'receipts';
  if (pathname.startsWith('/admin/po-management')) return 'po';
  return 'hub';
}

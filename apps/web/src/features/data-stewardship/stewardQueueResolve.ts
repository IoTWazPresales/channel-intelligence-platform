export type StewardResolveEngine = 'dsi' | 'cst' | 'shipment';

export function stewardResolveEngine(entityType: string): StewardResolveEngine | null {
  if (
    entityType === 'product_identifier' ||
    entityType === 'customer_dealer_token' ||
    entityType === 'distributor_token'
  ) {
    return 'dsi';
  }
  if (entityType === 'cst_product_token' || entityType === 'cst_location_token') {
    return 'cst';
  }
  if (entityType === 'shipment_distributor' || entityType === 'shipment_customer_token') {
    return 'shipment';
  }
  return null;
}

export function dsiTabForEntityType(entityType: string): 'distributor' | 'customer' | 'product' | null {
  if (entityType === 'distributor_token') return 'distributor';
  if (entityType === 'customer_dealer_token') return 'customer';
  if (entityType === 'product_identifier') return 'product';
  return null;
}

export function cstTabForEntityType(entityType: string): 'product' | 'location' | null {
  if (entityType === 'cst_product_token') return 'product';
  if (entityType === 'cst_location_token') return 'location';
  return null;
}

export function shipmentTabForEntityType(entityType: string): 'distributor' | 'customer' | null {
  if (entityType === 'shipment_distributor') return 'distributor';
  if (entityType === 'shipment_customer_token') return 'customer';
  return null;
}

export function parsePositiveInt(raw: string | null): number | null {
  if (raw == null || raw.trim() === '') return null;
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number.parseInt(raw.trim(), 10);
  return n >= 1 ? n : null;
}

/** Canonical API fields not shown in the default grid — operator can add via the column picker. */
export const SHIPMENT_EVIDENCE_OPTIONAL_FIELDS: { field: string; label: string }[] = [
  { field: 'operating_unit', label: 'Operating unit' },
  { field: 'ship_to_raw', label: 'Ship to' },
  { field: 'order_no', label: 'Order no.' },
  { field: 'order_line', label: 'Order line' },
  { field: 'delivery_no', label: 'Delivery no.' },
  { field: 'invoice_line', label: 'Invoice line' },
  { field: 'customer_item', label: 'Customer item' },
  { field: 'ean_code', label: 'EAN' },
  { field: 'upc_code', label: 'UPC' },
  { field: 'mpor_item_no', label: 'MPOR item no.' },
  { field: 'unit_price', label: 'Unit price' },
  { field: 'schedule_ship_date', label: 'Schedule ship' },
  { field: 'promise_date', label: 'Promise date' },
  { field: 'exwork_date', label: 'Ex-work date' },
  { field: 'erd_date', label: 'ERD date' },
  { field: 'est_pod_date', label: 'Est. POD date' },
  { field: 'pod_date', label: 'POD date' },
  { field: 'product_id', label: 'Product ID' },
  { field: 'product_resolution_token', label: 'Product resolution token' },
  { field: 'product_resolution_detail', label: 'Product resolution detail' },
  { field: 'distributor_id', label: 'Distributor ID' },
  { field: 'distributor_resolution_token', label: 'Distributor resolution token' },
  { field: 'created_at', label: 'Created at' },
];

export const SHIPMENT_EVIDENCE_OPTIONAL_FIELD_SET = new Set(SHIPMENT_EVIDENCE_OPTIONAL_FIELDS.map((c) => c.field));

/** Raw import keys share the picker with canonical fields; prefix keeps the two id spaces disjoint. */
export const RAW_KEY_PREFIX = 'raw:';

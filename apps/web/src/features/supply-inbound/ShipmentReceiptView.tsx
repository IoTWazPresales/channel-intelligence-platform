'use client';

import { Alert, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import NextLink from 'next/link';

export type ReceiptLine = {
  id: number;
  order_no: string | null;
  order_line: string | null;
  delivery_no: string | null;
  item_code: string | null;
  sales_model_name: string | null;
  product_sku: string | null;
  quantity: number | null;
  line_state: string | null;
  pod_date: string | null;
  cancelled_candidate?: boolean;
};

export type ReceiptEvent = {
  event_type: string;
  valid_from: string;
  details: Record<string, unknown>;
};

export type ShipmentReceipt = {
  id: number;
  group: 'delivery' | 'order' | 'line';
  title: string;
  pod_recorded: boolean;
  pod_date: string | null;
  est_pod_date: string | null;
  lines: ReceiptLine[];
  events: ReceiptEvent[];
};

const EVENT_LABEL: Record<string, string> = {
  date_slip: 'Date moved',
  qty_change: 'Quantity changed',
  graduated: 'Graduated to a numbered invoice',
  pod_reversal: 'Proof of delivery cleared',
  cancelled_candidate: 'Cancelled candidate',
};

function eventDetail(event: ReceiptEvent): string {
  const d = event.details || {};
  if (event.event_type === 'date_slip') {
    return `${String(d.date_field || 'date')} ${String(d.prior_date || '—')} → ${String(d.current_date || '—')}`;
  }
  if (event.event_type === 'qty_change') {
    return `${String(d.prior_quantity ?? '—')} → ${String(d.current_quantity ?? '—')}`;
  }
  if (event.event_type === 'pod_reversal') {
    return `Was ${String(d.prior_pod_date || 'recorded')}`;
  }
  if (event.event_type === 'cancelled_candidate') {
    return `${String(d.item_code || 'Line')} was on an earlier report and is missing from the latest report for this shipment.`;
  }
  return '';
}

export function ShipmentReceiptView({ receipt }: { receipt: ShipmentReceipt }) {
  return (
    <Stack spacing={2} data-testid="shipment-receipt" sx={{ mt: 2 }}>
      <Typography variant="h6">{receipt.title}</Typography>
      <Link component={NextLink} href="/supply/shipments">
        Back to shipments
      </Link>
      <Typography variant="body2" data-testid="shipment-receipt-pod">
        {receipt.pod_recorded
          ? `Proof of delivery ${receipt.pod_date}.`
          : 'No proof of delivery.'}
        {receipt.est_pod_date ? ` Expected ${receipt.est_pod_date}.` : ''}
      </Typography>
      <Typography variant="subtitle2">Lines on this shipment</Typography>
      <Table size="small" data-testid="shipment-receipt-lines">
        <TableHead>
          <TableRow>
            <TableCell>Item</TableCell>
            <TableCell>Order</TableCell>
            <TableCell align="right">Quantity</TableCell>
            <TableCell>Proof of delivery</TableCell>
            <TableCell>Signal</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {receipt.lines.map((line) => (
            <TableRow key={line.id}>
              <TableCell>{line.product_sku || line.item_code || line.sales_model_name || '—'}</TableCell>
              <TableCell>
                {[line.order_no, line.order_line].filter(Boolean).join(' / ') || '—'}
              </TableCell>
              <TableCell align="right">{line.quantity ?? '—'}</TableCell>
              <TableCell>{line.pod_date || 'None'}</TableCell>
              <TableCell>
                {line.cancelled_candidate ? 'Cancelled candidate' : '—'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography variant="subtitle2">Changes</Typography>
      {receipt.events.length === 0 ? (
        <Alert severity="info" data-testid="shipment-receipt-timeline">
          No changes recorded for this shipment.
        </Alert>
      ) : (
        <Stack spacing={1} data-testid="shipment-receipt-timeline">
          {receipt.events.map((event, index) => (
            <Typography key={`${event.valid_from}-${index}`} variant="body2">
              {event.valid_from.replace('T', ' ').slice(0, 19)} · {EVENT_LABEL[event.event_type] || event.event_type}
              {eventDetail(event) ? ` · ${eventDetail(event)}` : ''}
            </Typography>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

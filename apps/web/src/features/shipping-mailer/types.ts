export type ShippingMailerRecipient = {
  id: number;
  tenant_id: string;
  address: string;
  display_name: string | null;
  enabled: boolean;
  added_by: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ShippingMailerRecipientList = {
  items: ShippingMailerRecipient[];
};

export const SHIPPING_MAILER_RECIPIENTS_QUERY_KEY = ['shipping-mailer', 'recipients'] as const;

export const RECIPIENTS_PATH = '/api/v1/shipping-mailer/recipients';

export function looksLikeEmail(value: string): boolean {
  const trimmed = value.trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
}

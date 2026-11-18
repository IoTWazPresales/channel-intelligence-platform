/** Final wave (c): one aged-stock line per customer and product, with its sites folded underneath. */

export type AgedLine = {
  customer_id: number;
  /** Name only; codes never go in the customer column. */
  customer_name?: string | null;
  product_id: number;
  sku?: string | null;
  product_name?: string | null;
  site_label?: string | null;
  stock_on_hand?: number | null;
  slow?: boolean;
  unsold?: boolean;
  suggestions?: string[];
  suggestion_executed?: boolean;
  executed_actions?: string[];
};

export type AgedReason = 'slow' | 'unsold';

export type AgedProductGroup = {
  key: string;
  customer_id: number;
  customer_name?: string | null;
  product_id: number;
  sku?: string | null;
  product_name?: string | null;
  /** Sum over the sites that report stock; null when none does. */
  stock_on_hand: number | null;
  reasons: AgedReason[];
  sites: AgedLine[];
};

function siteKey(label: string | null | undefined): string {
  return (label ?? '').trim().toLowerCase().split(/\s+/).filter(Boolean).join(' ');
}

export function lineReasons(line: AgedLine): AgedReason[] {
  const out: AgedReason[] = [];
  if (line.slow) out.push('slow');
  if (line.unsold) out.push('unsold');
  return out;
}

export function groupAgedLines(lines: AgedLine[]): AgedProductGroup[] {
  const groups = new Map<string, AgedProductGroup>();
  const seenSites = new Map<string, Set<string>>();
  for (const line of lines) {
    const key = `${line.customer_id}-${line.product_id}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        customer_id: line.customer_id,
        customer_name: line.customer_name,
        product_id: line.product_id,
        sku: line.sku,
        product_name: line.product_name,
        stock_on_hand: null,
        reasons: [],
        sites: [],
      };
      groups.set(key, group);
      seenSites.set(key, new Set());
    }
    const sites = seenSites.get(key)!;
    const sk = siteKey(line.site_label);
    if (sites.has(sk)) continue;
    sites.add(sk);
    group.sites.push(line);
    if (line.stock_on_hand != null)
      group.stock_on_hand = (group.stock_on_hand ?? 0) + Number(line.stock_on_hand);
    for (const reason of lineReasons(line))
      if (!group.reasons.includes(reason)) group.reasons.push(reason);
  }
  for (const group of groups.values()) {
    group.reasons.sort();
    if (group.stock_on_hand != null)
      group.stock_on_hand = Math.round(group.stock_on_hand * 100) / 100;
  }
  return [...groups.values()];
}

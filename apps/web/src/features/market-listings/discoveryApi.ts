'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost, apiPut, safeDisplayError } from '@/lib/api';

import { customersListUrl } from './listingCustomerScope';

const ROOT = '/api/v1/listing-capture/discovery';

export type ProviderId = 'ddg_html' | 'ddg_lite' | 'searxng' | 'ddgs_auto';
export type DiscoveryProvider = { id: ProviderId; label: string; needs_url: boolean };
export type DiscoveryCapabilities = {
  live_fetch: boolean;
  browser_available: boolean;
  providers: DiscoveryProvider[];
  settings: { missing: string[] };
};

export type PreviewRequest =
  | { scope: 'customer'; customer_id: number }
  | { scope: 'reporting' }
  | { scope: 'domain'; customer_id: number; domain: string }
  | { scope: 'unlinked_listings'; customer_id: number | null };

export type SiteEvidence = {
  sources?: string[];
  name_match?: { exact: boolean; customer_keys?: string[]; domain_key?: string };
  ending_match?: string | null;
  country_match?: { value: boolean; how?: string | null };
  homepage?: {
    http_status?: number | null;
    final_url?: string | null;
    title?: string | null;
    org_name?: string | null;
    match?: boolean;
  };
  product_search_hits?: {
    product_id: number;
    product_label?: string;
    query?: string;
    rank?: number;
  }[];
  robots?: string;
  redirected_from?: string;
};

export type ProductCandidate = { product_id: number; label: string };
export type PageFacts = {
  barcodes?: string[];
  models?: string[];
  stock_codes?: string[];
  brand?: string | null;
};

export type DiscoveryPage = {
  item_id: string;
  product_id: number | null;
  product_label?: string | null;
  url?: string | null;
  outcome: string;
  how?: string | null;
  reason?: string | null;
  candidates?: ProductCandidate[];
  facts?: PageFacts;
  capture?: {
    price?: number | null;
    availability?: string | null;
    seller?: string | null;
  } | null;
};

export type DiscoveryListing = DiscoveryPage & {
  listing_id: number;
  customer_id: number;
  customer_name: string;
};

export type DiscoveryCustomer = {
  customer_id: number;
  customer_name: string;
  reporting: boolean;
  notes: string[];
  candidates: {
    item_id: string;
    domain: string;
    outcome: string;
    drop_reason?: string | null;
    proposed_site_key?: string;
    evidence: SiteEvidence;
  }[];
  sites: {
    domain: string;
    site_key: string;
    state: string;
    search_pattern?: { value: string | null; how: string };
    fetch?: { stopped: string | null; requests: number };
    pages: DiscoveryPage[];
  }[];
};

export type DiscoveryResult = {
  scope: PreviewRequest['scope'];
  created_at: string;
  finished_at?: string | null;
  stopped?: string | null;
  settings: {
    country: { code: string; name: string } | null;
    domain_endings: string[];
    search_providers: ProviderId[];
  };
  search: {
    status: 'ok' | 'empty' | 'unavailable' | 'off' | 'not_used';
    provider_used: string | null;
    attempts: {
      provider: string | null;
      status: string;
      http_status?: number | null;
      reason?: string | null;
    }[];
  };
  customers: DiscoveryCustomer[];
  listings: DiscoveryListing[];
  totals: {
    sites_auto: number;
    sites_review: number;
    pages_auto: number;
    pages_review: number;
    listings_auto: number;
    listings_review: number;
  };
};

export type ApplyResult = {
  sites_confirmed: number;
  sites_queued: number;
  sites_created: number;
  pages_linked: number;
  proposals_created: number;
  pages_queued: number;
  listings_linked: number;
  listings_queued: number;
  skipped: { item_id: string; reason: string }[];
  applied_at?: string;
};

export type DiscoveryPlan = {
  preview_id: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'expired';
  progress: { done: number; total: number };
  applied: ApplyResult | null;
  result: DiscoveryResult | null;
  error?: string | null;
};

export type SiteCandidate = {
  id: number;
  customer_id: number;
  customer_name: string;
  domain: string;
  evidence: SiteEvidence;
  created_at: string | null;
};

export type SearchOptions = {
  min_interval_seconds: number;
  max_results: number;
  timeout_seconds: number;
  region?: string;
};

export type ListingScope = {
  enabled: boolean;
  recent_window_days: number;
  recent_interval_days: number;
  absent_days: number;
};

export type DiscoverySettingValues = {
  'listing_scope.settings': ListingScope;
  'tenant.country': { code: string; name: string };
  'tenant.domain_endings': string[];
  'discovery.search_providers': ProviderId[];
  'discovery.search_options': SearchOptions;
  'discovery.searxng_url': string;
  'discovery.excluded_domains': string[];
  'discovery.browser_fallback_enabled': boolean;
  'discovery.schedule_enabled': boolean;
  'discovery.scheduled_run_debounce_hours': number;
  'discovery.confirm_coalesce_seconds': number;
  'discovery.matrix_customer_ids': number[];
  'tenant.locale': string;
};
export type DiscoverySettingKey = keyof DiscoverySettingValues;
export type SettingWrite = {
  [K in DiscoverySettingKey]: { key: K; value: DiscoverySettingValues[K] };
}[DiscoverySettingKey];
export type TenantSettings = {
  settings: Partial<DiscoverySettingValues>;
  known_keys: string[];
};

export type CustomerPick = { id: number; customer_name: string; customer_code?: string };
export type ProductPick = { id: number; sku: string; name: string };

/** Full directory search (add non-reporting customers to a scope). */
export async function fetchCustomers(q: string, signal: AbortSignal): Promise<CustomerPick[]> {
  const page = await apiGet<{ items?: CustomerPick[] }>(customersListUrl(false, { q: q || undefined }), { signal });
  return page.items ?? [];
}

/** Reporting customers only (default scope). */
export async function fetchReportingCustomers(signal: AbortSignal): Promise<CustomerPick[]> {
  const page = await apiGet<{ items?: CustomerPick[] }>(customersListUrl(true), { signal });
  return page.items ?? [];
}

/** EntitySearchAutocomplete: reporting list when empty; full directory when query length ≥ 2. */
export async function fetchDiscoveryCustomerOptions(q: string, signal: AbortSignal): Promise<CustomerPick[]> {
  const trimmed = q.trim();
  if (trimmed.length >= 2) return fetchCustomers(trimmed, signal);
  return fetchReportingCustomers(signal);
}

export async function fetchProducts(q: string, signal: AbortSignal): Promise<ProductPick[]> {
  const page = await apiGet<{ items?: ProductPick[] }>(
    `/api/v1/products?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
    { signal },
  );
  return page.items ?? [];
}

export const customerLabel = (row: CustomerPick) => row.customer_name || 'Unnamed customer';
export const productLabel = (row: ProductPick) => `${row.sku} ${row.name}`.trim();

export function webUrl(value: string | null | undefined): boolean {
  return Boolean(value && /^https?:\/\//i.test(value));
}

const REASONS: Record<string, string> = {
  ambiguous_identity: 'More than one product matched',
  no_identity_on_page: 'No barcode or model was found on the page',
  page_unreadable: 'The page could not be read',
  identity_mismatch: 'The page matched a different product',
  time_limit: 'The time available for this check was reached',
  over_review_limit: 'Other candidates were placed ahead of this one for review',
  changed_since_preview: 'The saved records changed after this preview',
  already_in_review: 'Already in the review queue. Nothing new to save.',
  robots: 'The site does not allow this page to be checked',
  search_not_installed: 'Web search is not available on this server',
  settings_changed: 'Settings changed. Start a new preview before saving.',
  preview_expired: 'This preview expired. Start a new preview.',
  preview_not_done: 'This preview has not finished.',
};

export function discoveryReason(value: string | null | undefined): string {
  return value ? REASONS[value] ?? value.replaceAll('_', ' ') : '';
}

export function discoveryError(error: unknown): string {
  const message = safeDisplayError(error);
  try {
    const body = JSON.parse(message) as { code?: string; message?: string };
    return discoveryReason(body.code) || body.message || 'The request could not be completed.';
  } catch {
    return discoveryReason(message);
  }
}

const SETTINGS_MISSING_LABELS: Record<string, string> = {
  'tenant.country': 'Set the tenant country in Settings → Discovery.',
  'tenant.domain_endings': 'Set domain endings in Settings → Discovery.',
};

export type PreviewGateOpts = {
  busy?: boolean;
  capabilitiesLoading?: boolean;
  capabilitiesError?: boolean;
  customerPicked?: boolean;
  siteCustomerPicked?: boolean;
  domainFilled?: boolean;
};

/** Human-readable reason a Discover/Preview control stays disabled, or null when it may run. */
export function previewBlockReason(
  capabilities: DiscoveryCapabilities | undefined,
  scope: PreviewRequest['scope'],
  opts: PreviewGateOpts = {},
): string | null {
  if (opts.busy) return 'A discovery preview is already running.';
  if (opts.capabilitiesLoading) return 'Checking discovery availability…';
  if (opts.capabilitiesError) return 'Discovery availability could not be loaded.';
  if (!capabilities?.live_fetch) {
    return 'Live page checking is off on this server. Enable CIP_LISTING_LIVE_FETCH in apps/api/.env (or on the worker).';
  }
  const missing = capabilities.settings.missing;
  if (scope !== 'unlinked_listings' && missing.includes('tenant.country')) {
    return SETTINGS_MISSING_LABELS['tenant.country'];
  }
  if (
    (scope === 'customer' || scope === 'reporting') &&
    missing.includes('tenant.domain_endings')
  ) {
    return SETTINGS_MISSING_LABELS['tenant.domain_endings'];
  }
  if (scope === 'customer' && !opts.customerPicked) return 'Choose a customer to discover.';
  if (scope === 'domain') {
    if (!opts.siteCustomerPicked) return 'Choose the customer for this site.';
    if (!opts.domainFilled) return 'Enter a domain to discover.';
  }
  return null;
}

export function previewAllowed(
  capabilities: DiscoveryCapabilities | undefined,
  scope: PreviewRequest['scope'],
  opts: PreviewGateOpts = {},
): boolean {
  return previewBlockReason(capabilities, scope, opts) === null;
}

function useDiscoveryKeys() {
  const me = useCurrentUser();
  const owner = [me.data?.tenant_id ?? '', me.data?.id ?? ''];
  return {
    ready: Boolean(me.data),
    root: ['listing-capture', 'discovery', ...owner] as const,
    settings: ['tenant-settings', ...owner] as const,
  };
}

export function useDiscoveryCapabilities() {
  const keys = useDiscoveryKeys();
  return useQuery({
    queryKey: [...keys.root, 'capabilities'],
    queryFn: ({ signal }) => apiGet<DiscoveryCapabilities>(`${ROOT}/capabilities`, { signal }),
    enabled: keys.ready,
    retry: false,
  });
}

export function useStartDiscoveryPreview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PreviewRequest) =>
      apiPost<{ preview_id: string; status: 'queued' }>(`${ROOT}/previews`, body),
    retry: false,
    onError: () => {
      void qc.invalidateQueries({ queryKey: ['listing-capture', 'discovery'] });
    },
  });
}

export function useDiscoveryPreview(previewId: string) {
  const keys = useDiscoveryKeys();
  return useQuery({
    queryKey: [...keys.root, 'preview', previewId],
    queryFn: ({ signal }) =>
      apiGet<DiscoveryPlan>(`${ROOT}/previews/${encodeURIComponent(previewId)}`, { signal }),
    enabled: keys.ready && Boolean(previewId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === 'queued' || query.state.data?.status === 'running' ? 2000 : false,
  });
}

export function useApplyDiscoveryPreview(previewId: string) {
  const keys = useDiscoveryKeys();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<ApplyResult>(`${ROOT}/previews/${encodeURIComponent(previewId)}/apply`),
    retry: false,
    onSuccess: async (applied) => {
      qc.setQueryData<DiscoveryPlan>([...keys.root, 'preview', previewId], (old) =>
        old ? { ...old, applied } : old,
      );
      await qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
}

export function useSiteCandidates() {
  const keys = useDiscoveryKeys();
  return useQuery({
    queryKey: [...keys.root, 'site-candidates', 'proposed'],
    queryFn: ({ signal }) =>
      apiGet<{ items: SiteCandidate[] }>(`${ROOT}/site-candidates?status=proposed`, { signal }),
    enabled: keys.ready,
    retry: false,
  });
}

export function useDecideSiteCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'confirm' | 'reject' }) =>
      apiPost<{ id: number; status: string; site_created: boolean }>(
        `${ROOT}/site-candidates/${id}`,
        { action },
      ),
    retry: false,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
}

export function useDiscoverySettings() {
  const keys = useDiscoveryKeys();
  return useQuery({
    queryKey: keys.settings,
    queryFn: ({ signal }) => apiGet<TenantSettings>('/api/v1/tenant-settings', { signal }),
    enabled: keys.ready,
    retry: false,
  });
}

export function useSaveDiscoverySetting() {
  const keys = useDiscoveryKeys();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: SettingWrite) =>
      apiPut<{ key: DiscoverySettingKey; value: DiscoverySettingValues[DiscoverySettingKey] }>(
        `/api/v1/tenant-settings/${encodeURIComponent(key)}`,
        { value },
      ),
    retry: false,
    onSuccess: async ({ key, value }) => {
      qc.setQueryData<TenantSettings>(keys.settings, (old) => ({
        known_keys: old?.known_keys ?? [],
        settings: { ...old?.settings, [key]: value },
      }));
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'discovery'] });
    },
  });
}

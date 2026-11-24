'use client';

import { Alert, Box, Button, Divider, Stack, TextField, Typography } from '@mui/material';
import { useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel } from '@/features/workbench-ui/Panel';

import {
  customerLabel, type CustomerPick, discoveryError, fetchDiscoveryCustomerOptions, previewAllowed, previewBlockReason,
  type PreviewRequest, useDiscoveryCapabilities, useStartDiscoveryPreview,
} from './discoveryApi';
import { DiscoveryPreview } from './DiscoveryPreview';
import { SiteCandidatesQueue } from './SiteCandidatesQueue';

export function DiscoveryLens() {
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  return <DiscoveryWorkspace key={`${me.data?.tenant_id}:${me.data?.id}`} canEdit={canEdit} />;
}

function DiscoveryWorkspace({ canEdit }: { canEdit: boolean }) {
  const capabilities = useDiscoveryCapabilities();
  const start = useStartDiscoveryPreview();
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  const [siteCustomer, setSiteCustomer] = useState<CustomerPick | null>(null);
  const [domain, setDomain] = useState('');
  const [previewId, setPreviewId] = useState<string | null>(null);
  const busy = start.isPending || Boolean(previewId);
  const gateOpts = {
    busy,
    capabilitiesLoading: capabilities.isPending,
    capabilitiesError: capabilities.isError,
    customerPicked: Boolean(customer),
    siteCustomerPicked: Boolean(siteCustomer),
    domainFilled: Boolean(domain.trim()),
  };
  const disabled = (scope: PreviewRequest['scope']) =>
    !previewAllowed(capabilities.data, scope, gateOpts);
  const blockReason = (scope: PreviewRequest['scope']) => {
    const reason = previewBlockReason(capabilities.data, scope, gateOpts);
    if (!reason) return null;
    if (capabilities.data && !capabilities.data.live_fetch) return null;
    return reason;
  };
  const run = (request: PreviewRequest) =>
    start.mutate(request, { onSuccess: (response) => setPreviewId(response.preview_id) });

  return (
    <Stack spacing={2} sx={{ mt: 2, minWidth: 0 }} data-testid="discovery-lens">
      <Typography variant="body2" color="text.secondary">
        Find customer sites and product pages. Preview checks the evidence; Apply saves only after you review it.
      </Typography>
      {capabilities.isPending ? <Typography variant="body2">Checking discovery availability…</Typography> : null}
      {capabilities.isError ? (
        <Alert severity="error" action={<Button color="inherit" onClick={() => void capabilities.refetch()}>Retry</Button>}>
          Discovery availability could not be loaded. {discoveryError(capabilities.error)}
        </Alert>
      ) : null}
      {capabilities.data?.settings.missing.length ? (
        <Alert severity="warning" action={<Button color="inherit" href="/settings#discovery">Settings → Discovery</Button>}>
          Discovery needs the tenant country and domain endings. Set them in Settings → Discovery.
        </Alert>
      ) : null}
      {capabilities.data && !capabilities.data.live_fetch ? (
        <Alert severity="info">
          Live page checking is off on this server. Set CIP_LISTING_LIVE_FETCH in apps/api/.env (or enable it on the worker)
          so Discover can run previews.
        </Alert>
      ) : null}
      {start.isError ? <Alert severity="error">{discoveryError(start.error)}</Alert> : null}
      {canEdit ? (
        <Panel title="Start a discovery" subtitle="Nothing is saved by any Preview button.">
          <Stack spacing={1.5} divider={<Divider />}>
            <Stack spacing={1}>
              <Typography variant="subtitle2">Discover for one customer</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <EntitySearchAutocomplete<CustomerPick> label="Customer to discover" size="small"
                    value={customer} onChange={setCustomer} fetchOptions={fetchDiscoveryCustomerOptions}
                    getOptionLabel={customerLabel} disabled={busy} />
                </Box>
                <Button variant="outlined" aria-label="Discover one customer" disabled={disabled('customer')}
                  onClick={() => customer && run({ scope: 'customer', customer_id: customer.id })}>Discover</Button>
              </Stack>
              {blockReason('customer') ? (
                <Typography variant="caption" color="text.secondary" data-testid="discover-customer-reason">
                  {blockReason('customer')}
                </Typography>
              ) : null}
            </Stack>
            <Stack spacing={0.5}>
              <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
                <Typography variant="subtitle2">Discover for all reporting customers</Typography>
                <Button variant="outlined" aria-label="Discover all reporting customers" disabled={disabled('reporting')}
                  onClick={() => run({ scope: 'reporting' })}>Discover</Button>
              </Stack>
              {blockReason('reporting') ? (
                <Typography variant="caption" color="text.secondary" data-testid="discover-reporting-reason">
                  {blockReason('reporting')}
                </Typography>
              ) : null}
            </Stack>
            <Stack spacing={1}>
              <Typography variant="subtitle2">Add a site to monitor</Typography>
              <Typography variant="caption" color="text.secondary">Choose any customer, including one that does not report, and enter a domain.</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <EntitySearchAutocomplete<CustomerPick> label="Customer for this site" size="small"
                    value={siteCustomer} onChange={setSiteCustomer} fetchOptions={fetchDiscoveryCustomerOptions}
                    getOptionLabel={customerLabel} disabled={busy} />
                </Box>
                <TextField size="small" label="Domain" value={domain} disabled={busy}
                  onChange={(event) => setDomain(event.target.value)}
                  helperText="Host name only, such as shop.example.test" sx={{ flex: 1 }} />
                <Button variant="outlined" aria-label="Discover a site" disabled={disabled('domain')}
                  onClick={() => siteCustomer && run({ scope: 'domain', customer_id: siteCustomer.id, domain: domain.trim() })}>Discover</Button>
              </Stack>
              {blockReason('domain') ? (
                <Typography variant="caption" color="text.secondary">{blockReason('domain')}</Typography>
              ) : null}
            </Stack>
            <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
              <Typography variant="subtitle2">Link listings with no product</Typography>
              <Button variant="outlined" aria-label="Discover listings with no product" disabled={disabled('unlinked_listings')}
                onClick={() => run({ scope: 'unlinked_listings', customer_id: null })}>Discover</Button>
            </Stack>
          </Stack>
        </Panel>
      ) : <Alert severity="info">A steward can start previews and save discovery results.</Alert>}
      {previewId ? (
        <DiscoveryPreview key={previewId} previewId={previewId} canEdit={canEdit}
          providers={capabilities.data?.providers} onDiscard={() => { setPreviewId(null); start.reset(); }} />
      ) : null}
      <SiteCandidatesQueue />
    </Stack>
  );
}

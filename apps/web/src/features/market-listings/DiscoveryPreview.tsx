'use client';

import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, Dialog,
  DialogActions, DialogContent, DialogTitle, LinearProgress, Link, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
} from '@mui/material';
import { useState } from 'react';

import { Panel } from '@/features/workbench-ui/Panel';

import {
  discoveryError, discoveryReason, type DiscoveryPage, type DiscoveryProvider,
  useApplyDiscoveryPreview, useDiscoveryPreview, webUrl,
} from './discoveryApi';
import { DiscoveryEvidence } from './SiteCandidatesQueue';

export function DiscoveryPageLink({ url }: { url?: string | null }) {
  return url && webUrl(url) ? (
    <Link href={url} target="_blank" rel="noopener noreferrer" sx={{ overflowWrap: 'anywhere' }}>
      {url}
    </Link>
  ) : <Typography variant="body2">{url || 'No page found'}</Typography>;
}

function Outcome({ outcome, how, reason }: { outcome: string; how?: string | null; reason?: string | null }) {
  let label = discoveryReason(outcome);
  let color: 'default' | 'success' | 'warning' = 'default';
  if (outcome === 'auto_accept' || outcome === 'user_confirmed') {
    label = 'Will be added';
    color = 'success';
  } else if (outcome === 'auto_link') {
    label = `Will be linked${how ? ` (${how === 'gtin' ? 'barcode' : how === 'feed_seed' ? 'saved feed mapping' : discoveryReason(how)})` : ''}`;
    color = 'success';
  } else if (outcome === 'steward_queue') {
    label = 'Goes to review';
    color = 'warning';
  } else if (outcome === 'already_monitored') label = 'Already monitored';
  else if (outcome === 'already_rejected' || outcome === 'rejected_before') label = 'Rejected before';
  else if (outcome === 'already_linked') label = 'Already linked';
  else if (outcome === 'not_found') label = 'No page found';
  else if (outcome === 'needs_browser') {
    label = 'Needs a browser';
    color = 'warning';
  } else if (outcome === 'dropped') label = 'Not usable';
  return (
    <Stack spacing={0.5} alignItems="flex-start">
      <Chip label={label} color={color} size="small" />
      {reason ? <Typography variant="caption">{discoveryReason(reason)}</Typography> : null}
    </Stack>
  );
}

function PageRows({ pages }: { pages: DiscoveryPage[] }) {
  return (
    <TableContainer>
      <Table size="small" aria-label="Product pages found" sx={{ minWidth: 680 }}>
        <TableHead><TableRow>
          <TableCell>Product</TableCell><TableCell>Page link</TableCell>
          <TableCell>After Apply</TableCell><TableCell>Price / stock</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {pages.map((page) => (
            <TableRow key={page.item_id}>
              <TableCell>{page.product_label || 'Product not yet linked'}</TableCell>
              <TableCell sx={{ maxWidth: 300 }}><DiscoveryPageLink url={page.url} /></TableCell>
              <TableCell>
                <Outcome outcome={page.outcome} how={page.how} reason={page.reason} />
                {page.facts?.barcodes?.length ? <Typography variant="caption" display="block">Barcodes: {page.facts.barcodes.join(', ')}</Typography> : null}
                {page.facts?.models?.length ? <Typography variant="caption" display="block">Models: {page.facts.models.join(', ')}</Typography> : null}
                {page.candidates?.length ? <Typography variant="caption" display="block">Possible products: {page.candidates.map((c) => c.label).join(', ')}</Typography> : null}
              </TableCell>
              <TableCell>
                {page.capture?.price == null ? 'Price not found' : page.capture.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                <Typography variant="caption" display="block">
                  {page.capture?.availability ? discoveryReason(page.capture.availability) : 'Stock not found'}
                </Typography>
                {page.capture?.seller ? <Typography variant="caption">{page.capture.seller}</Typography> : null}
              </TableCell>
            </TableRow>
          ))}
          {pages.length === 0 ? <TableRow><TableCell colSpan={4}>No product pages found in this preview.</TableCell></TableRow> : null}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export function DiscoveryPreview({
  previewId, canEdit, providers = [], onDiscard,
}: {
  previewId: string;
  canEdit: boolean;
  providers?: DiscoveryProvider[];
  onDiscard: () => void;
}) {
  const preview = useDiscoveryPreview(previewId);
  const apply = useApplyDiscoveryPreview(previewId);
  const [confirm, setConfirm] = useState(false);
  const plan = preview.data;
  const result = plan?.result;
  const applied = apply.data ?? plan?.applied;
  const running = plan?.status === 'queued' || plan?.status === 'running';
  const totals = result?.totals;
  const reviewCount = totals ? totals.sites_review + totals.pages_review + totals.listings_review : 0;
  const providerLabel = (id: string | null) => providers.find((p) => p.id === id)?.label || 'Search provider';
  const searchUnavailable = result?.search.status === 'unavailable' || result?.search.status === 'off';

  return (
    <Panel title="Discovery preview" subtitle="Review what will be saved, then choose Apply.">
      <Stack spacing={2} data-testid="discovery-preview" sx={{ minWidth: 0 }}>
        {!applied ? <Alert severity="info">Nothing saved yet. Preview only checks sites and pages. Apply saves the results you reviewed.</Alert> : null}
        {preview.isPending ? <LinearProgress aria-label="Loading preview" /> : null}
        {preview.isError ? (
          <Alert severity="error" action={<Button color="inherit" onClick={() => void preview.refetch()}>Retry</Button>}>
            {discoveryError(preview.error)}
          </Alert>
        ) : null}
        {running ? (
          <Stack spacing={1} aria-live="polite">
            <LinearProgress aria-label="Checking customers" />
            <Typography variant="body2">Checked {plan.progress.done} of {plan.progress.total} customers</Typography>
          </Stack>
        ) : null}
        {plan?.status === 'failed' ? (
          <Alert severity="error">
            {plan.error === 'settings_missing'
              ? <>Discovery settings are missing. <Link href="/settings#discovery">Open Settings → Discovery</Link>.</>
              : 'This preview could not finish. Discard it and start a new preview.'}
          </Alert>
        ) : null}
        {plan?.status === 'expired' ? <Alert severity="warning">This preview expired. Discard it and start a new preview.</Alert> : null}
        {apply.isError ? <Alert severity="error">{discoveryError(apply.error)} Retry Apply to check the saved result, or start a new preview if requested.</Alert> : null}
        {applied ? (
          <Alert severity="success" data-testid="discovery-applied">
            Saved: {applied.sites_confirmed} sites confirmed ({applied.sites_created} new), {applied.pages_linked} pages linked,
            {' '}{applied.listings_linked} listings linked, {applied.proposals_created} listing proposals created.
            {' '}Queued for review: {applied.sites_queued} sites, {applied.pages_queued} pages, {applied.listings_queued} listings.
            {applied.skipped.map((item) => (
              <Typography key={item.item_id} variant="body2">Skipped {item.item_id}: {discoveryReason(item.reason)}</Typography>
            ))}
          </Alert>
        ) : null}
        {result ? (
          <>
            <Typography variant="body2" color="text.secondary">
              Country: {result.settings.country?.name || 'Not set'} · Domain endings: {result.settings.domain_endings.join(', ') || 'Not set'}
            </Typography>
            <Alert severity={searchUnavailable ? 'warning' : 'info'}>
              {result.search.status === 'off' ? 'Web search is off. ' : result.search.status === 'unavailable' ? 'Web search was unavailable. ' : result.search.status === 'not_used' ? 'Web search was not needed. ' : result.search.status === 'empty' ? 'Web search found no results. ' : `Web search completed${result.search.provider_used ? ` using ${providerLabel(result.search.provider_used)}` : ''}. `}
              {searchUnavailable
                ? result.scope === 'domain'
                  ? 'This preview checks the site you entered.'
                  : result.scope === 'unlinked_listings'
                    ? 'This preview checks the saved listing links.'
                    : 'Results come from sites on file, contact email domains and name guesses only.'
                : null}
              {result.search.attempts.map((attempt, index) => (
                <Typography key={index} variant="body2">
                  {providerLabel(attempt.provider)}: {discoveryReason(attempt.status)}
                  {attempt.http_status != null ? ` (${attempt.http_status})` : ''}
                  {attempt.reason ? ` — ${discoveryReason(attempt.reason)}` : ''}
                </Typography>
              ))}
            </Alert>
            {result.stopped ? <Alert severity="warning">This preview stopped early: {discoveryReason(result.stopped)}. Only the results shown will be saved.</Alert> : null}
            {result.customers.map((customer) => (
              <Accordion key={customer.customer_id} defaultExpanded>
                <AccordionSummary expandIcon={<Box component="span">⌄</Box>}>
                  <Typography variant="subtitle2">{customer.customer_name || 'Unnamed customer'}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1.5} sx={{ minWidth: 0 }}>
                    {customer.notes.map((note, index) => <Typography key={index} variant="body2" color="text.secondary">{note}</Typography>)}
                    <TableContainer>
                      <Table size="small" aria-label={`Candidate sites for ${customer.customer_name}`} sx={{ minWidth: 640 }}>
                        <TableHead><TableRow><TableCell>Domain</TableCell><TableCell>After Apply</TableCell><TableCell>Match evidence</TableCell></TableRow></TableHead>
                        <TableBody>
                          {customer.candidates.map((candidate) => (
                            <TableRow key={candidate.item_id}>
                              <TableCell sx={{ overflowWrap: 'anywhere' }}>{candidate.domain}</TableCell>
                              <TableCell><Outcome outcome={candidate.outcome} reason={candidate.drop_reason} /></TableCell>
                              <TableCell><DiscoveryEvidence evidence={candidate.evidence} /></TableCell>
                            </TableRow>
                          ))}
                          {customer.candidates.length === 0 ? <TableRow><TableCell colSpan={3}>No candidate sites found.</TableCell></TableRow> : null}
                        </TableBody>
                      </Table>
                    </TableContainer>
                    {customer.sites.map((site) => (
                      <Stack key={site.domain} spacing={1}>
                        <Typography variant="subtitle2">Product pages on {site.domain}</Typography>
                        {site.fetch?.stopped ? <Alert severity="warning">Checks stopped: {discoveryReason(site.fetch.stopped)}</Alert> : null}
                        <PageRows pages={site.pages} />
                      </Stack>
                    ))}
                  </Stack>
                </AccordionDetails>
              </Accordion>
            ))}
            {result.scope === 'unlinked_listings' || result.listings.length > 0 ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2">Listings with no product</Typography>
                {result.listings.map((listing) => (
                  <Box key={listing.item_id}>
                    <Typography variant="body2">{listing.customer_name || 'Unnamed customer'}</Typography>
                    <PageRows pages={[listing]} />
                  </Box>
                ))}
                {result.listings.length === 0 ? <Typography variant="body2">No listings need a product link.</Typography> : null}
              </Stack>
            ) : null}
            {totals ? (
              <Typography variant="body2" data-testid="discovery-preview-totals">
                After Apply: {totals.sites_auto} sites added, {totals.pages_auto} pages linked,
                {' '}{totals.listings_auto} listings linked, {reviewCount} items sent for review.
              </Typography>
            ) : null}
          </>
        ) : null}
        <Stack direction="row" spacing={1}>
          {canEdit ? (
            <Button variant="contained" disabled={plan?.status !== 'done' || !result || Boolean(applied) || apply.isPending || preview.isError}
              onClick={() => setConfirm(true)}>Apply</Button>
          ) : null}
          <Button variant="outlined" disabled={apply.isPending} onClick={onDiscard}>Discard</Button>
        </Stack>
        <Typography variant="caption" color="text.secondary">Discard closes this preview. A running check will finish without saving its results.</Typography>
      </Stack>
      <Dialog open={confirm} onClose={() => setConfirm(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Save discovery results?</DialogTitle>
        <DialogContent>
          Save {totals?.sites_auto ?? 0} sites, link {totals?.pages_auto ?? 0} pages
          and {totals?.listings_auto ?? 0} listings, and queue {reviewCount} items for review?
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="contained" disabled={!canEdit || plan?.status !== 'done' || !result || Boolean(applied) || apply.isPending}
            onClick={() => { setConfirm(false); apply.mutate(); }}>Save results</Button>
        </DialogActions>
      </Dialog>
    </Panel>
  );
}

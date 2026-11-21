'use client';

import { Alert, Button, Chip, Stack, Typography } from '@mui/material';

import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel } from '@/features/workbench-ui/Panel';

import {
  discoveryError,
  discoveryReason,
  type SiteEvidence,
  useDecideSiteCandidate,
  useSiteCandidates,
} from './discoveryApi';

const SOURCES: Record<string, string> = {
  on_file: 'On file',
  email: 'Contact email domain',
  product_search: 'Product search',
  name_search: 'Customer name search',
  guess: 'Name guess',
  user: 'Entered by you',
};
const COUNTRY: Record<string, string> = {
  cctld: 'domain ending',
  page_locale: 'page language setting',
  address_country: 'page address',
};

export function DiscoveryEvidence({ evidence }: { evidence: SiteEvidence }) {
  const hits = evidence.product_search_hits ?? [];
  const chips = [
    evidence.name_match
      ? evidence.name_match.exact ? 'Name matches' : 'Name does not match exactly'
      : 'Name not checked',
    evidence.country_match
      ? evidence.country_match.value
        ? `Country matches${evidence.country_match.how ? ` (${COUNTRY[evidence.country_match.how] ?? discoveryReason(evidence.country_match.how)})` : ''}`
        : 'Country not matched'
      : 'Country not checked',
    evidence.ending_match ? `Domain ending: ${evidence.ending_match}` : 'Domain ending: not set or not matched',
    ...(evidence.homepage?.match ? ['Home page matches'] : []),
    ...(hits.length ? [`Found by product search (${hits.length})`] : []),
    ...(evidence.sources ?? []).map((source) => SOURCES[source] ?? discoveryReason(source)),
    ...(evidence.robots ? [`Page access: ${discoveryReason(evidence.robots)}`] : []),
  ];
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
        {[...new Set(chips)].map((label) => <Chip key={label} label={label} size="small" variant="outlined" />)}
      </Stack>
      {evidence.homepage?.title ? <Typography variant="caption">{evidence.homepage.title}</Typography> : null}
      {evidence.homepage?.org_name ? <Typography variant="caption">Page name: {evidence.homepage.org_name}</Typography> : null}
      {evidence.homepage?.http_status != null ? (
        <Typography variant="caption">Home page response: {evidence.homepage.http_status}</Typography>
      ) : null}
      {evidence.redirected_from ? (
        <Typography variant="caption">Redirected from {evidence.redirected_from}</Typography>
      ) : null}
      {hits.map((hit, index) => (
        <Typography key={`${hit.product_id}-${index}`} variant="caption" sx={{ overflowWrap: 'anywhere' }}>
          {hit.product_label || 'Product'}{hit.query ? ` — ${hit.query}` : ''}
          {hit.rank != null ? ` (result ${hit.rank})` : ''}
        </Typography>
      ))}
    </Stack>
  );
}

export function SiteCandidatesQueue() {
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  const queue = useSiteCandidates();
  const decide = useDecideSiteCandidate();
  return (
    <Panel title="Site candidates waiting for review" subtitle="Confirm the customer’s site, or reject it so it is not proposed again.">
      <Stack spacing={1.5} data-testid="site-candidates-queue">
        {queue.isPending ? <Typography variant="body2">Loading site candidates…</Typography> : null}
        {queue.isError ? (
          <Alert severity="error" action={<Button color="inherit" onClick={() => void queue.refetch()}>Retry</Button>}>
            {discoveryError(queue.error)}
          </Alert>
        ) : null}
        {decide.isError ? <Alert severity="error">{discoveryError(decide.error)}</Alert> : null}
        {decide.isSuccess ? <Alert severity="success">Decision saved.</Alert> : null}
        {queue.isSuccess && queue.data.items.length === 0 ? (
          <Typography variant="body2">No sites waiting for review.</Typography>
        ) : null}
        {(queue.data?.items ?? []).map((item) => (
          <Stack key={item.id} spacing={1} data-testid={`site-candidate-${item.id}`}
            sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5, minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ overflowWrap: 'anywhere' }}>
              {item.customer_name || 'Unnamed customer'} · {item.domain}
            </Typography>
            <DiscoveryEvidence evidence={item.evidence} />
            {canEdit ? (
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="contained" disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: item.id, action: 'confirm' })}>Confirm</Button>
                <Button size="small" variant="outlined" disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: item.id, action: 'reject' })}>Reject</Button>
              </Stack>
            ) : null}
          </Stack>
        ))}
      </Stack>
    </Panel>
  );
}

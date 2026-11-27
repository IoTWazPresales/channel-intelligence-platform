'use client';

import {
  Alert, Box, Button, Checkbox, Divider, FormControlLabel, Stack, Switch, TextField, Typography,
} from '@mui/material';
import { useState } from 'react';

import {
  type DiscoveryCapabilities, type DiscoverySettingKey, type DiscoverySettingValues,
  discoveryError, type ProviderId, type SettingWrite,
  useDiscoveryCapabilities, useDiscoverySettings, useSaveDiscoverySetting,
} from '@/features/market-listings/discoveryApi';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel } from '@/features/workbench-ui/Panel';

const lines = (text: string) => text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

export function DiscoverySettingsPanel() {
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  return canEdit ? <DiscoverySettings key={`${me.data?.tenant_id}:${me.data?.id}`} /> : null;
}

function DiscoverySettings() {
  const settings = useDiscoverySettings();
  const capabilities = useDiscoveryCapabilities();
  return (
    <Box id="discovery" sx={{ scrollMarginTop: 80 }} data-testid="discovery-settings">
      <Panel title="Discovery" subtitle="Settings belong to this tenant. Save each field when you are ready.">
        {settings.isPending || capabilities.isPending ? <Typography variant="body2">Loading discovery settings…</Typography> : null}
        {settings.isError || capabilities.isError ? (
          <Alert severity="error" action={<Button color="inherit" onClick={() => {
            void settings.refetch();
            void capabilities.refetch();
          }}>Retry</Button>}>
            {discoveryError(settings.error ?? capabilities.error)}
          </Alert>
        ) : settings.data && capabilities.data ? (
          <DiscoverySettingsForm initial={settings.data.settings} capabilities={capabilities.data} />
        ) : null}
      </Panel>
    </Box>
  );
}

function DiscoverySettingsForm({
  initial, capabilities,
}: { initial: Partial<DiscoverySettingValues>; capabilities: DiscoveryCapabilities }) {
  const [country, setCountry] = useState(initial['tenant.country'] ?? { code: '', name: '' });
  const [endings, setEndings] = useState((initial['tenant.domain_endings'] ?? []).join('\n'));
  const [providers, setProviders] = useState<ProviderId[]>(initial['discovery.search_providers'] ?? []);
  const [url, setUrl] = useState(initial['discovery.searxng_url'] ?? '');
  const savedOptions = initial['discovery.search_options'];
  const [gap, setGap] = useState(savedOptions ? String(savedOptions.min_interval_seconds) : '');
  const [maxResults, setMaxResults] = useState(savedOptions ? String(savedOptions.max_results) : '');
  const [timeout, setTimeoutValue] = useState(savedOptions ? String(savedOptions.timeout_seconds) : '');
  const [region, setRegion] = useState(savedOptions?.region ?? '');
  const savedDebounce = initial['discovery.scheduled_run_debounce_hours'];
  const savedCoalesce = initial['discovery.confirm_coalesce_seconds'];
  const [debounceHours, setDebounceHours] = useState(savedDebounce != null ? String(savedDebounce) : '');
  const [coalesceSeconds, setCoalesceSeconds] = useState(savedCoalesce != null ? String(savedCoalesce) : '');
  const [debounceOnFile, setDebounceOnFile] = useState(savedDebounce != null);
  const [coalesceOnFile, setCoalesceOnFile] = useState(savedCoalesce != null);
  const [excluded, setExcluded] = useState((initial['discovery.excluded_domains'] ?? []).join('\n'));
  const [browser, setBrowser] = useState(initial['discovery.browser_fallback_enabled'] === true);
  const [scheduled, setScheduled] = useState(initial['discovery.schedule_enabled'] === true);
  const savedScope = initial['listing_scope.settings'];
  // Suggested values only (Warren, 24 Nov 2026); nothing is stored until Save is pressed.
  const [scopeOn, setScopeOn] = useState(savedScope?.enabled === true);
  const [windowDays, setWindowDays] = useState(String(savedScope?.recent_window_days ?? 180));
  const [intervalDays, setIntervalDays] = useState(String(savedScope?.recent_interval_days ?? 7));
  const [absentDays, setAbsentDays] = useState(String(savedScope?.absent_days ?? 14));
  const [errors, setErrors] = useState<Partial<Record<DiscoverySettingKey, string>>>({});
  const [saved, setSaved] = useState(false);
  const save = useSaveDiscoverySetting();
  const needsUrl = capabilities.providers.some((provider) => provider.needs_url && providers.includes(provider.id));
  const ordered = [
    ...providers.map((id) => capabilities.providers.find((provider) => provider.id === id)).filter((p) => p != null),
    ...capabilities.providers.filter((provider) => !providers.includes(provider.id)),
  ];

  function write(body: SettingWrite) {
    setSaved(false);
    setErrors((old) => ({ ...old, [body.key]: undefined }));
    save.mutate(body, {
      onSuccess: () => {
        setSaved(true);
        if (body.key === 'discovery.scheduled_run_debounce_hours') setDebounceOnFile(true);
        if (body.key === 'discovery.confirm_coalesce_seconds') setCoalesceOnFile(true);
      },
      onError: (error) => setErrors((old) => ({ ...old, [body.key]: discoveryError(error) })),
    });
  }
  function move(id: ProviderId, offset: number) {
    const index = providers.indexOf(id);
    if (index < 0 || index + offset < 0 || index + offset >= providers.length) return;
    const next = [...providers];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    setProviders(next);
  }
  const helper = (key: DiscoverySettingKey, present: boolean, text = '') =>
    errors[key] || (present ? text : `Not set${text ? `. ${text}` : ''}`);
  const saveButton = (label: string, body: SettingWrite, disabled = false) => (
    <Box><Button size="small" variant="outlined" disabled={save.isPending || disabled}
      onClick={() => write(body)}>{label}</Button></Box>
  );

  return (
    <Stack spacing={2} divider={<Divider />} sx={{ maxWidth: 760 }}>
      {saved ? <Alert severity="success">Saved.</Alert> : null}
      <Stack spacing={1}>
        <Typography variant="subtitle2">Tenant country</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField size="small" label="Country code" value={country.code} disabled={save.isPending}
            onChange={(event) => setCountry({ ...country, code: event.target.value.toUpperCase() })}
            error={Boolean(errors['tenant.country'])}
            helperText={helper('tenant.country', Boolean(country.code), 'Two capital letters')} />
          <TextField size="small" label="Country name" value={country.name} disabled={save.isPending}
            onChange={(event) => setCountry({ ...country, name: event.target.value })}
            error={Boolean(errors['tenant.country'])}
            helperText={helper('tenant.country', Boolean(country.name))} sx={{ flex: 1 }} />
        </Stack>
        {saveButton('Save country', { key: 'tenant.country', value: country })}
      </Stack>
      <Stack spacing={1}>
        <TextField size="small" label="Domain endings" value={endings} multiline minRows={2} disabled={save.isPending}
          onChange={(event) => setEndings(event.target.value)} error={Boolean(errors['tenant.domain_endings'])}
          helperText={helper('tenant.domain_endings', Boolean(endings.trim()), 'One per line, starting with a dot. Order is the order checked.')} />
        {saveButton('Save domain endings', { key: 'tenant.domain_endings', value: lines(endings) })}
      </Stack>
      <Stack spacing={1}>
        <Typography variant="subtitle2">Search providers</Typography>
        <Typography variant="caption" color="text.secondary">
          Recommended: DuckDuckGo (HTML), then DuckDuckGo (Lite). Nothing is selected or saved for you.
        </Typography>
        {providers.length === 0 ? <Typography variant="body2">Not set. Web search is off.</Typography> : null}
        {ordered.map((provider) => {
          const index = providers.indexOf(provider.id);
          return (
            <Stack key={provider.id} direction="row" alignItems="center" spacing={1}>
              <FormControlLabel sx={{ flex: 1 }} label={provider.label}
                control={<Checkbox checked={index >= 0} disabled={save.isPending} onChange={(_, checked) =>
                  setProviders(checked ? [...providers, provider.id] : providers.filter((id) => id !== provider.id))} />} />
              <Button size="small" aria-label={`Move ${provider.label} up`} disabled={save.isPending || index <= 0}
                onClick={() => move(provider.id, -1)}>Up</Button>
              <Button size="small" aria-label={`Move ${provider.label} down`}
                disabled={save.isPending || index < 0 || index === providers.length - 1}
                onClick={() => move(provider.id, 1)}>Down</Button>
            </Stack>
          );
        })}
        {errors['discovery.search_providers'] ? <Alert severity="error">{errors['discovery.search_providers']}</Alert> : null}
        {needsUrl ? (
          <Stack spacing={1}>
            <TextField size="small" label="SearXNG URL" value={url} disabled={save.isPending}
              onChange={(event) => setUrl(event.target.value)} error={Boolean(errors['discovery.searxng_url'])}
              helperText={helper('discovery.searxng_url', Boolean(url.trim()), 'Use your HTTPS server address without a query string. Save it before saving the provider order.')} />
            {saveButton('Save SearXNG URL', { key: 'discovery.searxng_url', value: url.trim() })}
          </Stack>
        ) : null}
        {saveButton('Save search providers', { key: 'discovery.search_providers', value: providers })}
      </Stack>
      <Stack spacing={1}>
        <Typography variant="subtitle2">Search pacing</Typography>
        <Typography variant="caption" color="text.secondary">Web search needs these three numbers. Nothing is filled in for you.</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField size="small" type="number" label="Seconds between searches" value={gap} disabled={save.isPending}
            onChange={(event) => setGap(event.target.value)} error={Boolean(errors['discovery.search_options'])}
            helperText={helper('discovery.search_options', Boolean(savedOptions))} />
          <TextField size="small" type="number" label="Results per search" value={maxResults} disabled={save.isPending}
            onChange={(event) => setMaxResults(event.target.value)} error={Boolean(errors['discovery.search_options'])} />
          <TextField size="small" type="number" label="Search timeout (seconds)" value={timeout} disabled={save.isPending}
            onChange={(event) => setTimeoutValue(event.target.value)} error={Boolean(errors['discovery.search_options'])} />
          <TextField size="small" label="Search region (optional)" value={region} disabled={save.isPending}
            onChange={(event) => setRegion(event.target.value)} error={Boolean(errors['discovery.search_options'])} />
        </Stack>
        {saveButton('Save search options', { key: 'discovery.search_options', value: {
          min_interval_seconds: Number(gap), max_results: Number(maxResults), timeout_seconds: Number(timeout),
          ...(region.trim() ? { region: region.trim() } : {}),
        } }, !gap.trim() || !maxResults.trim() || !timeout.trim())}
        <Typography variant="caption" color="text.secondary">
          Scheduled discovery needs both timings below. Nothing is filled in for you.
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField size="small" type="number" label="Hours between scheduled runs" value={debounceHours} disabled={save.isPending}
            onChange={(event) => setDebounceHours(event.target.value)} error={Boolean(errors['discovery.scheduled_run_debounce_hours'])}
            helperText={helper('discovery.scheduled_run_debounce_hours', savedDebounce != null)} />
          <TextField size="small" type="number" label="Seconds to wait after a site confirm" value={coalesceSeconds} disabled={save.isPending}
            onChange={(event) => setCoalesceSeconds(event.target.value)} error={Boolean(errors['discovery.confirm_coalesce_seconds'])}
            helperText={helper('discovery.confirm_coalesce_seconds', savedCoalesce != null)} />
        </Stack>
        {saveButton('Save hours between runs', { key: 'discovery.scheduled_run_debounce_hours', value: Number(debounceHours) }, !debounceHours.trim())}
        {saveButton('Save confirm wait', { key: 'discovery.confirm_coalesce_seconds', value: Number(coalesceSeconds) }, !coalesceSeconds.trim())}
      </Stack>
      <Stack spacing={1}>
        <TextField size="small" label="Excluded domains" value={excluded} multiline minRows={2} disabled={save.isPending}
          onChange={(event) => setExcluded(event.target.value)} error={Boolean(errors['discovery.excluded_domains'])}
          helperText={helper('discovery.excluded_domains', Boolean(excluded.trim()), 'One host name per line. These sites will not be proposed.')} />
        {saveButton('Save excluded domains', { key: 'discovery.excluded_domains', value: lines(excluded) })}
      </Stack>
      <Stack spacing={1}>
        <Typography variant="subtitle2">Listing monitoring scope</Typography>
        <Typography variant="caption" color="text.secondary">
          Active products (in stock, on order, inbound or at a distributor) are checked on the normal schedule.
          Recently gone products are checked less often. Older products are not checked; use Fetch now on a listing.
          {savedScope ? '' : ' Not set: every listing is checked. The numbers are suggestions and are saved only when you press Save.'}
        </Typography>
        <FormControlLabel label="Limit monitoring by stock" control={
          <Switch checked={scopeOn} disabled={save.isPending} onChange={(_, checked) => setScopeOn(checked)} />} />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField size="small" type="number" label="Recently gone window (days)" value={windowDays} disabled={save.isPending}
            onChange={(event) => setWindowDays(event.target.value)} error={Boolean(errors['listing_scope.settings'])}
            helperText={errors['listing_scope.settings']} />
          <TextField size="small" type="number" label="Check recently gone every (days)" value={intervalDays} disabled={save.isPending}
            onChange={(event) => setIntervalDays(event.target.value)} error={Boolean(errors['listing_scope.settings'])} />
          <TextField size="small" type="number" label="Days missing before a product drops" value={absentDays} disabled={save.isPending}
            onChange={(event) => setAbsentDays(event.target.value)} error={Boolean(errors['listing_scope.settings'])} />
        </Stack>
        {saveButton('Save monitoring scope', { key: 'listing_scope.settings', value: {
          enabled: scopeOn, recent_window_days: Number(windowDays), recent_interval_days: Number(intervalDays),
          absent_days: Number(absentDays),
        } }, !windowDays.trim() || !intervalDays.trim() || !absentDays.trim())}
      </Stack>
      <Stack spacing={1}>
        <FormControlLabel label="Use a browser when a page needs one" control={
          <Switch checked={browser} disabled={save.isPending || !capabilities.browser_available}
            onChange={(_, checked) => setBrowser(checked)} />
        } />
        {!capabilities.browser_available ? <Typography variant="caption">Not installed on the server</Typography> : null}
        {errors['discovery.browser_fallback_enabled'] ? <Alert severity="error">{errors['discovery.browser_fallback_enabled']}</Alert> : null}
        {saveButton('Save browser setting', { key: 'discovery.browser_fallback_enabled', value: browser }, !capabilities.browser_available)}
      </Stack>
      <Stack spacing={1}>
        <FormControlLabel label="Scheduled discovery (off by default)" control={
          <Switch checked={scheduled} disabled={save.isPending} onChange={(_, checked) => setScheduled(checked)} />
        } />
        <Typography variant="caption" color="text.secondary">Continue product-page checks on saved sites automatically. New sites still require Apply or a review decision.</Typography>
        {errors['discovery.schedule_enabled'] ? <Alert severity="error">{errors['discovery.schedule_enabled']}</Alert> : null}
        {saveButton(
          'Save scheduled discovery',
          { key: 'discovery.schedule_enabled', value: scheduled },
          scheduled && (!debounceOnFile || !coalesceOnFile),
        )}
      </Stack>
    </Stack>
  );
}

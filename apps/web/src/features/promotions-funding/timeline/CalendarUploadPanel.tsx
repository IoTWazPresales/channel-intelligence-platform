'use client';

import { Alert, Button, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ImportFileUploadZone } from '@/app/(app)/admin/imports/ImportFileUploadZone';
import { CanonicalColumnMappingPanel } from '@/features/import-mapping/CanonicalColumnMappingPanel';
import { apiDelete, apiGet, apiPost, apiPostFormData, apiPut } from '@/lib/api';
import { applySelections, selectionProblems, selectionsFor } from './calendarMapping';
import type { CalendarKind, CalendarPreview, CalendarProfile } from './types';

const ROOT = '/api/v1/customer-calendar';
const PROFILE_KEY = ['customer-calendar', 'profiles'];
const targets = [
  { value: 'customer_token', label: 'Customer' }, { value: 'name', label: 'Event name' },
  { value: 'kind', label: 'Event kind' }, { value: 'start_date', label: 'Start date' }, { value: 'end_date', label: 'End date' },
];
const required = [{ id: 'name', label: 'Event name', anyOf: ['name'] }, { id: 'start', label: 'Start date', anyOf: ['start_date'] }];
type Props = { customerId: number; onApplied: () => void };

export function CalendarUploadPanel(props: Props) {
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const query = useQuery({ queryKey: PROFILE_KEY,
    queryFn: ({ signal }) => apiGet<{ profiles: CalendarProfile[]; data_unavailable?: boolean; message?: string }>(`${ROOT}/profiles`, { signal }),
  });
  const profiles = query.data?.profiles ?? [];
  const selected = profiles.find(p => p.profile_code === selectedCode) ?? profiles.find(p => p.is_default) ?? profiles[0];
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={2}>
    <Typography variant="h6">Upload customer calendar</Typography>
    <Typography variant="body2">All events in this upload will be assigned to the selected customer. Reuse a saved column mapping, preview the events, then apply.</Typography>
    {query.error && <Alert severity="error">{query.error.message}</Alert>}
    {query.data?.data_unavailable && <Alert severity="info">{query.data.message}</Alert>}
    {query.isPending && <Typography>Loading mapping profiles...</Typography>}
    {selected && <>
      <TextField select label="Mapping profile" value={selected.profile_code} onChange={e => setSelectedCode(e.target.value)}>
        {profiles.map(p => <MenuItem key={p.profile_code} value={p.profile_code}>{p.display_name}</MenuItem>)}
      </TextField>
      <CalendarUploadEditor key={selected.profile_code} {...props} profile={selected} onSelect={setSelectedCode} />
    </>}
  </Stack></Paper>;
}

function CalendarUploadEditor({ customerId, onApplied, profile, onSelect }: Props & { profile: CalendarProfile; onSelect: (code: string) => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File>();
  const [uploadId, setUploadId] = useState('');
  const [preview, setPreview] = useState<CalendarPreview | null>(null);
  const [draft, setDraft] = useState(profile);
  const [kindAliases, setKindAliases] = useState(Object.entries(profile.value_maps_json.kind ?? {}).map(([k, v]) => `${k}=${v}`).join('\n'));
  const [newCode, setNewCode] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [headers, setHeaders] = useState<string[]>([]);
  const [selection, setSelection] = useState<Record<string, string>>({});
  const builtIn = profile.id === null;
  const problems = selectionProblems(headers, selection);

  function changeProfile(next: CalendarProfile) { setDraft(next); setDirty(true); setPreview(null); }
  async function action(run: () => Promise<void>) {
    setPending(true); setError(null); setMessage(null);
    try { await run(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setPending(false); }
  }
  function form() {
    const body = new FormData();
    body.set('file', file!); body.set('customer_id', String(customerId)); body.set('profile_code', draft.profile_code);
    const ref = uploadId.trim() || preview?.upload_id;
    if (ref) body.set('upload_id', ref);
    return body;
  }
  async function save(create: boolean) {
    await action(async () => {
      const kind: Record<string, CalendarKind> = {};
      for (const line of kindAliases.split('\n').filter(s => s.trim())) {
        const i = line.lastIndexOf('=');
        const key = line.slice(0, i).trim();
        const value = line.slice(i + 1).trim();
        if (i < 1 || !key || !['campaign', 'pillar', 'other'].includes(value)) throw new Error('Use source value=campaign, pillar or other for each kind alias.');
        kind[key] = value as CalendarKind;
      }
      const body = { ...draft, profile_code: create ? newCode.trim() : draft.profile_code, value_maps_json: { kind }, is_default: create ? false : draft.is_default };
      const saved = create || builtIn ? await apiPost<CalendarProfile>(`${ROOT}/profiles`, body) : await apiPut<CalendarProfile>(`${ROOT}/profiles/${profile.id}`, body);
      setDraft(saved); setDirty(false); setPreview(null); setMessage('Mapping profile saved. Preview the file again before applying.');
      await qc.invalidateQueries({ queryKey: PROFILE_KEY });
      onSelect(saved.profile_code);
    });
  }
  return <Stack spacing={2}>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
      <TextField label="Profile name" value={draft.display_name} disabled={pending} onChange={e => changeProfile({ ...draft, display_name: e.target.value })} />
      <TextField label="Header row" type="number" value={draft.header_row_index} inputProps={{ min: 1 }} disabled={pending} onChange={e => changeProfile({ ...draft, header_row_index: Number(e.target.value) })} />
      <TextField label="Worksheet (optional)" value={draft.sheet_name ?? ''} disabled={pending} onChange={e => changeProfile({ ...draft, sheet_name: e.target.value || null })} helperText="Leave blank for the first worksheet." />
    </Stack>
    <TextField label="Event kind aliases" multiline minRows={2} value={kindAliases} disabled={pending}
      helperText="One per line: source value=campaign, pillar or other. Unknown kinds become other."
      onChange={e => { setKindAliases(e.target.value); setDirty(true); setPreview(null); }} />
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Button disabled={pending || !dirty || builtIn || problems.length > 0} onClick={() => void save(false)}>Save profile</Button>
      <TextField size="small" label="New profile code" value={newCode} disabled={pending} onChange={e => setNewCode(e.target.value)} inputProps={{ maxLength: 64 }} />
      <Button disabled={pending || !newCode.trim() || problems.length > 0} onClick={() => void save(true)}>Create profile</Button>
      <Button color="error" disabled={pending || builtIn || profile.profile_code === 'customer_calendar_default_v1'} onClick={() => void action(async () => {
        await apiDelete(`${ROOT}/profiles/${profile.id}`); await qc.invalidateQueries({ queryKey: PROFILE_KEY });
      })}>Delete profile</Button>
    </Stack>
    <TextField label="Upload reference" value={uploadId} disabled={pending} inputProps={{ maxLength: 128 }}
      helperText="Reuse this reference to replace that upload for this customer. Leave blank to use the filename."
      onChange={e => { setUploadId(e.target.value); setPreview(null); }} />
    <ImportFileUploadZone expanded onExpandedChange={() => {}} canUpload={!pending} pending={pending}
      title="Drop a customer calendar CSV or XLSX here" testIdPrefix="calendar-upload"
      onFile={next => { if (pending) return; setFile(next); setPreview(null); setHeaders([]); setMessage(null); }} />
    {file && <Typography variant="body2">Selected file: {file.name}</Typography>}
    {builtIn && <Alert severity="info">This is the built-in generic mapping. To change it, enter a new profile code and choose Create profile.</Alert>}
    {dirty && <Alert severity="info">Save the mapping profile before previewing this file.</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {message && <Alert severity="success">{message}</Alert>}
    <Stack direction="row" spacing={1}>
      <Button variant="outlined" disabled={!file || pending || dirty} onClick={() => void action(async () => {
        setPreview(null);
        const out = await apiPostFormData<CalendarPreview>(`${ROOT}/upload/preview`, form());
        setHeaders(out.headers); setSelection(selectionsFor(draft.column_map_json, out.headers)); setPreview(out);
      })}>Preview calendar</Button>
      <Button variant="contained" disabled={!preview?.ok || pending || dirty} onClick={() => void action(async () => {
        const body = form(); body.set('confirm', 'true');
        const out = await apiPostFormData<{ inserted: number; replaced: number }>(`${ROOT}/upload/apply`, body);
        setPreview(null); setMessage(`Applied ${out.inserted} events; replaced ${out.replaced}.`); onApplied();
        await qc.invalidateQueries({ queryKey: ['customer-calendar', 'timeline'] });
      })}>Apply calendar</Button>
    </Stack>
    {problems.map(p => <Alert key={p} severity="error">{p}</Alert>)}
    {headers.length > 0 && <CanonicalColumnMappingPanel fileHeaders={headers} draft={selection} targetOptions={targets}
      requiredGroups={required} dirty={dirty} disabled={pending} testIdPrefix="calendar-map" onChange={picked => {
        // Each calendar field reads one column: choosing a column for a field moves it off the previous one.
        const next = { ...picked };
        const chosen = headers.find(h => next[h] && next[h] !== selection[h]);
        if (chosen) for (const h of headers) if (h !== chosen && next[h] === next[chosen]) delete next[h];
        setSelection(next);
        changeProfile({ ...draft, column_map_json: applySelections(draft.column_map_json, headers, next) });
      }} />}
    {preview && <Stack spacing={1}>
      <Typography>{preview.will_insert} events will be applied; {preview.will_replace} existing events will be replaced for this customer and upload.</Typography>
      {preview.blocking_errors.map(e => <Alert key={e.code} severity="error">{e.message}</Alert>)}
      {preview.row_errors.length > 0 && <Alert severity="warning">{preview.row_errors.length} invalid rows will be skipped.
        <ul>{preview.row_errors.map(e => <li key={`${e.row}-${e.code}`}>Row {e.row}: {e.message}</li>)}</ul>
      </Alert>}
      {preview.unresolved_customers.length > 0 && <Alert severity="warning">Unmatched customer rows will be skipped:
        {preview.unresolved_customers.map(c => ` ${c.token || '(blank)'} (${c.rows})`).join(', ')}
      </Alert>}
      {!preview.ok && <Alert severity="info">No events can be applied. Check the worksheet, header row and column mapping.</Alert>}
      <Table size="small" aria-label="Calendar preview"><TableHead><TableRow>
        <TableCell>Event</TableCell><TableCell>Kind</TableCell><TableCell>Start</TableCell><TableCell>End</TableCell>
      </TableRow></TableHead><TableBody>{preview.events.map(e => <TableRow key={e.row_number}>
        <TableCell>{e.name}</TableCell><TableCell>{e.kind}</TableCell><TableCell>{e.start_date}</TableCell><TableCell>{e.end_date}</TableCell>
      </TableRow>)}</TableBody></Table>
      {preview.events_truncated && <Typography variant="caption">Showing the first 200 events. Apply uses all valid events.</Typography>}
    </Stack>}
  </Stack>;
}

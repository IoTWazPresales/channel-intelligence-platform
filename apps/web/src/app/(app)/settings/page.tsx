'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { SemanticCatalogOverlayPanel } from '@/features/settings/SemanticCatalogOverlayPanel';
import { ShippingDigestRecipientsPanel } from '@/features/shipping-mailer';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost, apiPut, getApiBase, safeDisplayError } from '@/lib/api';
import { loadWipeAvailability } from '@/lib/wipeAvailability';
import { useUiStore } from '@/stores/uiStore';

const WIPE_CONFIRM_PHRASE = 'DELETE ALL APPLICATION DATA';

type ConstraintAxis = 'money' | 'support_pct' | 'dual' | 'none';
type OverBudgetAction = 'require_reapproval' | 'warn' | 'block';
type ReservationSource = 'derived_from_profit' | 'explicit_column' | 'hybrid';
type PmAttributionMode = 'business_line' | 'person_field' | 'none';

type LineupExportColumn = { field: string; header: string };

type ReportingCadence =
  | 'weekly_monday'
  | 'weekly_tuesday'
  | 'weekly_wednesday'
  | 'weekly_thursday'
  | 'weekly_friday'
  | 'weekly_saturday'
  | 'weekly_sunday'
  | 'daily';

type TenantCommercialProfile = {
  tenant_id: string;
  constraint_axis: ConstraintAxis;
  over_budget_action: OverBudgetAction;
  reservation_source: ReservationSource;
  pm_attribution_mode: PmAttributionMode;
  reporting_cadence?: ReportingCadence;
  woc_min_velocity_days?: number;
  lineup_export_sheets?: { net_requirement: string; draft_lineup: string };
  lineup_export_columns?: LineupExportColumn[];
  overrides_present: string[];
  hard_enforce_budget: boolean;
  money_ceiling_usd: number | null;
  support_norms_trailing_quarters: number;
};

const CONSTRAINT_AXIS_OPTIONS: ConstraintAxis[] = ['money', 'support_pct', 'dual', 'none'];
const OVER_BUDGET_ACTION_OPTIONS: OverBudgetAction[] = ['require_reapproval', 'warn', 'block'];
const RESERVATION_SOURCE_OPTIONS: ReservationSource[] = ['derived_from_profit', 'explicit_column', 'hybrid'];
const PM_ATTRIBUTION_MODE_OPTIONS: PmAttributionMode[] = ['business_line', 'person_field', 'none'];
const REPORTING_CADENCE_OPTIONS: ReportingCadence[] = [
  'weekly_monday',
  'weekly_tuesday',
  'weekly_wednesday',
  'weekly_thursday',
  'weekly_friday',
  'weekly_saturday',
  'weekly_sunday',
  'daily',
];

export default function SettingsPage() {
  const apiDisplay =
    getApiBase() ||
    'Same-origin /api/… (rewritten to FastAPI in next dev when NEXT_PUBLIC_API_URL is unset)';
  const density = useUiStore((s) => s.density);
  const qc = useQueryClient();
  const [wipeOpen, setWipeOpen] = useState(false);
  const [wipePhrase, setWipePhrase] = useState('');

  const { data: me } = useCurrentUser();
  const isAdmin = String(me?.role || '').toLowerCase() === 'admin';

  const tenantProfileQuery = useQuery({
    queryKey: ['auth', 'tenant-commercial-profile'],
    queryFn: () => apiGet<TenantCommercialProfile>('/api/v1/auth/tenant-commercial-profile'),
    staleTime: 30_000,
  });

  const [constraintAxis, setConstraintAxis] = useState<ConstraintAxis>('money');
  const [overBudgetAction, setOverBudgetAction] = useState<OverBudgetAction>('require_reapproval');
  const [reservationSource, setReservationSource] = useState<ReservationSource>('derived_from_profit');
  const [pmAttributionMode, setPmAttributionMode] = useState<PmAttributionMode>('business_line');
  const [reportingCadence, setReportingCadence] = useState<ReportingCadence>('weekly_monday');
  const [wocMinVelocityDays, setWocMinVelocityDays] = useState(90);
  const [exportNetReqSheet, setExportNetReqSheet] = useState('NetRequirement');
  const [exportDraftSheet, setExportDraftSheet] = useState('DraftLineup');
  const [exportColumns, setExportColumns] = useState<LineupExportColumn[]>([]);
  const [profileSaveOk, setProfileSaveOk] = useState<string | null>(null);
  const [profileSaveError, setProfileSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantProfileQuery.data) return;
    setConstraintAxis(tenantProfileQuery.data.constraint_axis);
    setOverBudgetAction(tenantProfileQuery.data.over_budget_action);
    setReservationSource(tenantProfileQuery.data.reservation_source);
    setPmAttributionMode(tenantProfileQuery.data.pm_attribution_mode);
    if (tenantProfileQuery.data.reporting_cadence) {
      setReportingCadence(tenantProfileQuery.data.reporting_cadence);
    }
    if (typeof tenantProfileQuery.data.woc_min_velocity_days === 'number') {
      setWocMinVelocityDays(tenantProfileQuery.data.woc_min_velocity_days);
    }
    const sheets = tenantProfileQuery.data.lineup_export_sheets;
    if (sheets?.net_requirement) setExportNetReqSheet(sheets.net_requirement);
    if (sheets?.draft_lineup) setExportDraftSheet(sheets.draft_lineup);
    if (tenantProfileQuery.data.lineup_export_columns?.length) {
      setExportColumns(tenantProfileQuery.data.lineup_export_columns);
    }
  }, [tenantProfileQuery.data]);

  const tenantProfileMutation = useMutation({
    mutationFn: () =>
      apiPut<TenantCommercialProfile>('/api/v1/auth/tenant-commercial-profile', {
        constraint_axis: constraintAxis,
        over_budget_action: overBudgetAction,
        reservation_source: reservationSource,
        pm_attribution_mode: pmAttributionMode,
        reporting_cadence: reportingCadence,
        woc_min_velocity_days: wocMinVelocityDays,
        lineup_export_net_requirement_sheet: exportNetReqSheet.trim() || undefined,
        lineup_export_draft_sheet: exportDraftSheet.trim() || undefined,
        lineup_export_columns: exportColumns.length ? exportColumns : undefined,
      }),
    onSuccess: async (data) => {
      setProfileSaveError(null);
      setProfileSaveOk('Saved.');
      qc.setQueryData(['auth', 'tenant-commercial-profile'], data);
    },
    onError: (err) => {
      setProfileSaveOk(null);
      setProfileSaveError(safeDisplayError(err));
    },
  });

  const { data: wipeStatus, isPending: wipeStatusPending } = useQuery({
    queryKey: ['dev-database-wipe-status'],
    queryFn: ({ signal }) => loadWipeAvailability(signal),
    staleTime: 30_000,
  });

  const wipeMutation = useMutation({
    mutationFn: () => apiPost<{ ok: boolean; rows_deleted: number }>('/api/v1/dev/database-wipe', { confirm: true }),
    onSuccess: async (data) => {
      setWipeOpen(false);
      setWipePhrase('');
      await qc.invalidateQueries();
      window.alert(`Database wiped. ${data.rows_deleted} row(s) deleted. Reload the page if grids look stale.`);
    },
  });

  const phraseOk = useMemo(() => wipePhrase.trim() === WIPE_CONFIRM_PHRASE, [wipePhrase]);

  return (
    <>
      <PageHeader {...navPageChrome('/settings')} />
      <Alert severity="info" sx={{ mb: 2 }}>
        Authentication and per-user preferences are not fully wired yet. Density is saved in the browser; API
        location is build-time for the web bundle.
      </Alert>
      <Paper sx={{ p: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          API base URL
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          <code style={{ wordBreak: 'break-all' }}>{apiDisplay}</code>
        </Typography>
        <Typography variant="caption" color="text.disabled">
          Set <code>NEXT_PUBLIC_API_URL</code> before <code>pnpm build</code> or in Docker build args to pin the API
          host. Leave it unset in <code>next dev</code> to use same-origin <code>/api/v1/…</code> (proxied by{' '}
          <code>src/app/api/v1/[[...path]]/route.ts</code> to FastAPI on <code>127.0.0.1:8000</code> by default).
        </Typography>
        <Divider sx={{ my: 3 }} />
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Table density
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" color="text.secondary">
            Current: <strong>{density}</strong> — toggle from the toolbar (compact rows icon).
          </Typography>
        </Stack>

        <Divider sx={{ my: 3 }} />
        <Typography variant="subtitle1" fontWeight={600} gutterBottom data-testid="tenant-profile-heading">
          Commercial tenant profile
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Tenant-variable commercial policy (BACKLOG-096). These four answers are onboarding
          decisions, not application law — do not assume they match another tenant. Saved
          overrides persist to <code>tenant_profiles/&lt;tenant_id&gt;.json</code> on the API host;
          unset fields fall back to the module defaults shown below.
        </Typography>
        {tenantProfileQuery.isError ? (
          <Alert severity="error" data-testid="tenant-profile-load-error">
            {safeDisplayError(tenantProfileQuery.error)}
          </Alert>
        ) : (
          <Stack spacing={2} maxWidth={480} data-testid="tenant-profile-form">
            {profileSaveError ? (
              <Alert severity="error" data-testid="tenant-profile-save-error">
                {profileSaveError}
              </Alert>
            ) : null}
            {profileSaveOk ? (
              <Alert severity="success" data-testid="tenant-profile-save-ok">
                {profileSaveOk}
              </Alert>
            ) : null}
            {!isAdmin ? (
              <Alert severity="info">Admin role required to edit — showing current values read-only.</Alert>
            ) : null}
            <FormControl fullWidth disabled={!isAdmin}>
              <InputLabel id="tenant-profile-constraint-axis-label">Constraint axis (Q-001)</InputLabel>
              <Select
                labelId="tenant-profile-constraint-axis-label"
                label="Constraint axis (Q-001)"
                value={constraintAxis}
                onChange={(ev) => setConstraintAxis(ev.target.value as ConstraintAxis)}
                inputProps={{ 'data-testid': 'tenant-profile-constraint-axis' }}
              >
                {CONSTRAINT_AXIS_OPTIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth disabled={!isAdmin}>
              <InputLabel id="tenant-profile-over-budget-action-label">Over-budget action</InputLabel>
              <Select
                labelId="tenant-profile-over-budget-action-label"
                label="Over-budget action"
                value={overBudgetAction}
                onChange={(ev) => setOverBudgetAction(ev.target.value as OverBudgetAction)}
                inputProps={{ 'data-testid': 'tenant-profile-over-budget-action' }}
              >
                {OVER_BUDGET_ACTION_OPTIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth disabled={!isAdmin}>
              <InputLabel id="tenant-profile-reservation-source-label">Reservation source (Q-002)</InputLabel>
              <Select
                labelId="tenant-profile-reservation-source-label"
                label="Reservation source (Q-002)"
                value={reservationSource}
                onChange={(ev) => setReservationSource(ev.target.value as ReservationSource)}
                inputProps={{ 'data-testid': 'tenant-profile-reservation-source' }}
              >
                {RESERVATION_SOURCE_OPTIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth disabled={!isAdmin}>
              <InputLabel id="tenant-profile-pm-attribution-mode-label">PM attribution mode (Q-009)</InputLabel>
              <Select
                labelId="tenant-profile-pm-attribution-mode-label"
                label="PM attribution mode (Q-009)"
                value={pmAttributionMode}
                onChange={(ev) => setPmAttributionMode(ev.target.value as PmAttributionMode)}
                inputProps={{ 'data-testid': 'tenant-profile-pm-attribution-mode' }}
              >
                {PM_ATTRIBUTION_MODE_OPTIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth disabled={!isAdmin}>
              <InputLabel id="tenant-profile-reporting-cadence-label">Reporting cadence (WoC)</InputLabel>
              <Select
                labelId="tenant-profile-reporting-cadence-label"
                label="Reporting cadence (WoC)"
                value={reportingCadence}
                onChange={(ev) => setReportingCadence(ev.target.value as ReportingCadence)}
                inputProps={{ 'data-testid': 'tenant-profile-reporting-cadence' }}
              >
                {REPORTING_CADENCE_OPTIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="WoC minimum velocity days"
              type="number"
              value={wocMinVelocityDays}
              onChange={(ev) => setWocMinVelocityDays(Number(ev.target.value))}
              disabled={!isAdmin}
              fullWidth
              helperText="Thin history below this writes NULL cover (clamp 28–90). Default 90."
              inputProps={{ 'data-testid': 'tenant-profile-woc-min-velocity-days', min: 28, max: 90 }}
            />
            <TextField
              label="Lineup export — Net requirement sheet"
              value={exportNetReqSheet}
              onChange={(ev) => setExportNetReqSheet(ev.target.value)}
              disabled={!isAdmin}
              fullWidth
              helperText="Workbook sheet title for net-requirement export (Lane B)."
              inputProps={{ 'data-testid': 'tenant-profile-export-net-req-sheet' }}
            />
            <TextField
              label="Lineup export — Draft lineup sheet"
              value={exportDraftSheet}
              onChange={(ev) => setExportDraftSheet(ev.target.value)}
              disabled={!isAdmin}
              fullWidth
              helperText="Workbook sheet title for draft lineup export."
              inputProps={{ 'data-testid': 'tenant-profile-export-draft-sheet' }}
            />
            <Typography variant="body2" color="text.secondary">
              Draft lineup export columns (canonical field → tenant header). Reorder or rename; field ids stay CIP.
            </Typography>
            {exportColumns.map((col, idx) => (
              <Stack key={col.field} direction="row" spacing={1} alignItems="center">
                <TextField
                  size="small"
                  label="Field"
                  value={col.field}
                  disabled
                  sx={{ width: 200 }}
                />
                <TextField
                  size="small"
                  label="Header"
                  value={col.header}
                  disabled={!isAdmin}
                  onChange={(ev) => {
                    const next = [...exportColumns];
                    next[idx] = { ...next[idx], header: ev.target.value };
                    setExportColumns(next);
                  }}
                  fullWidth
                  inputProps={{ 'data-testid': `tenant-profile-export-col-header-${col.field}` }}
                />
                <Button
                  size="small"
                  disabled={!isAdmin || idx === 0}
                  onClick={() => {
                    if (idx === 0) return;
                    const next = [...exportColumns];
                    [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                    setExportColumns(next);
                  }}
                >
                  Up
                </Button>
                <Button
                  size="small"
                  disabled={!isAdmin || idx === exportColumns.length - 1}
                  onClick={() => {
                    if (idx >= exportColumns.length - 1) return;
                    const next = [...exportColumns];
                    [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
                    setExportColumns(next);
                  }}
                >
                  Down
                </Button>
              </Stack>
            ))}
            {isAdmin ? (
              <Box>
                <Button
                  variant="contained"
                  disabled={tenantProfileMutation.isPending || tenantProfileQuery.isPending}
                  onClick={() => {
                    setProfileSaveOk(null);
                    setProfileSaveError(null);
                    tenantProfileMutation.mutate();
                  }}
                  data-testid="tenant-profile-save"
                >
                  {tenantProfileMutation.isPending ? 'Saving…' : 'Save tenant profile'}
                </Button>
              </Box>
            ) : null}
            {tenantProfileQuery.data ? (
              <Typography variant="caption" color="text.disabled">
                Overrides currently set: {tenantProfileQuery.data.overrides_present.length > 0
                  ? tenantProfileQuery.data.overrides_present.join(', ')
                  : 'none (using module defaults)'}
              </Typography>
            ) : null}
          </Stack>
        )}

        {isAdmin ? (
          <>
            <Divider sx={{ my: 3 }} />
            <ShippingDigestRecipientsPanel />
            <Divider sx={{ my: 3 }} />
            <SemanticCatalogOverlayPanel />
          </>
        ) : null}

        <Divider sx={{ my: 3 }} />
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Developer: wipe database
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Removes <strong>every row</strong> in all application tables (same as{' '}
          <code>python scripts/wipe_database.py</code> in the API repo). Schema stays; upload files on disk are
          unchanged. Restart the Celery worker after a wipe if you use background jobs.
        </Typography>
        {wipeStatusPending ? (
          <Typography variant="body2" color="text.secondary">
            Checking whether database wipe is available on this API…
          </Typography>
        ) : wipeStatus?.fetch_error ? (
          <Stack spacing={2}>
            <Alert severity="error">
              Could not read wipe status from <code>{apiDisplay}</code>: {wipeStatus.fetch_error}
              {wipeStatus.fetch_error.startsWith('404 ') ? (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  A <strong>404</strong> here usually means the process on <code>127.0.0.1:8000</code> (or your proxy
                  target) is <strong>not the API from this repository</strong>, or it is an <strong>older uvicorn</strong>{' '}
                  still holding the port. Run <code>pnpm dev:api</code> from a clean port (it refuses to start if the
                  port serves the wrong OpenAPI), or stop Docker/other Python on that port, then reload Settings.
                </Typography>
              ) : (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  If other pages load data, compare <code>NEXT_PUBLIC_API_URL</code> (build-time) to the API you are
                  actually running, and ensure this API version includes <code>GET /api/v1/dev/database-wipe</code>{' '}
                  (CORS must allow your web origin and Authorization headers).
                </Typography>
              )}
            </Alert>
            <Alert severity="warning">
              Wipe via the UI stays <strong>off</strong> until the status call succeeds. You can still wipe from a
              shell: <code>pnpm docker:db:wipe</code> / <code>pnpm docker:db:wipe:run</code>, or run{' '}
              <code>python scripts/wipe_database.py</code> from <code>apps/api</code> against your Postgres URL.
            </Alert>
          </Stack>
        ) : wipeStatus?.wipe_enabled ? (
          <>
            <Alert severity="error" sx={{ mb: 2 }}>
              Wipe is <strong>enabled</strong> on this API (<code>ALLOW_DB_WIPE=true</code>). Do not use on shared or
              production databases.
            </Alert>
            <Button variant="outlined" color="error" onClick={() => setWipeOpen(true)}>
              Open wipe confirmation…
            </Button>
          </>
        ) : (
          <Alert severity="warning">
            Wipe via the UI is <strong>disabled</strong> (<code>ALLOW_DB_WIPE</code> is not set on the API). On the API
            host, set <code>ALLOW_DB_WIPE=true</code>, restart the API, then reload this page. For Docker, uncomment{' '}
            <code>ALLOW_DB_WIPE</code> under the <code>api</code> service in <code>infra/docker/docker-compose.yml</code>{' '}
            or use <code>pnpm docker:db:wipe</code> / <code>pnpm docker:db:wipe:run</code> from the repo root instead.
          </Alert>
        )}
      </Paper>

      <Dialog open={wipeOpen} onClose={() => !wipeMutation.isPending && setWipeOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Wipe all application data?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This cannot be undone. Type the following phrase exactly (case-sensitive) to enable the button:
          </Typography>
          <Paper variant="outlined" sx={{ p: 1.5, mb: 2, bgcolor: 'action.hover' }}>
            <Typography variant="body2" fontFamily="monospace">
              {WIPE_CONFIRM_PHRASE}
            </Typography>
          </Paper>
          <TextField
            fullWidth
            label="Confirmation phrase"
            value={wipePhrase}
            onChange={(e) => setWipePhrase(e.target.value)}
            disabled={wipeMutation.isPending}
            autoComplete="off"
          />
          {wipeMutation.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {wipeMutation.error instanceof Error ? wipeMutation.error.message : String(wipeMutation.error)}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWipeOpen(false)} disabled={wipeMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={!phraseOk || wipeMutation.isPending}
            onClick={() => wipeMutation.mutate()}
          >
            {wipeMutation.isPending ? 'Wiping…' : 'Wipe database'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

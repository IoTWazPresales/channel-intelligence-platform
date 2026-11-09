'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, InputHTMLAttributes, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { UserRole } from '@cip/types';
import type { ColDef } from 'ag-grid-community';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost, apiPut, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type ListedUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  tenant_id: string;
  is_active: boolean;
  invite_sent?: boolean;
};

type UsersResponse = {
  tenant_id: string;
  users: ListedUser[];
};

const ROLES: UserRole[] = ['admin', 'steward', 'planner', 'viewer'];

type AccountChoice = { id: number; name: string };
type AccountScope = 'all' | 'selected';

const ACCOUNT_EMPTY_NOTE =
  'No accounts assigned means My accounts starts off. The person still sees the wider book their role and product lines allow. Assigning accounts turns the filter on at the next sign-in. Clear lasts for that sign-in only and does not hide the rest of the book.';

function AccountScopeControls({
  scope,
  onScope,
  selectedIds,
  onToggle,
  query,
  onQuery,
  options,
  scopeTestId,
}: {
  scope: AccountScope;
  onScope: (scope: AccountScope) => void;
  selectedIds: number[];
  onToggle: (id: number, name: string, checked: boolean) => void;
  query: string;
  onQuery: (value: string) => void;
  options: AccountChoice[];
  scopeTestId: 'edit' | 'create';
}) {
  const allId = scopeTestId === 'edit' ? 'users-account-scope-all' : 'users-create-account-scope-all';
  const selectedId = scopeTestId === 'edit' ? 'users-account-scope-selected' : 'users-create-account-scope-selected';
  return (
    <Stack spacing={1}>
      <RadioGroup value={scope} onChange={(ev) => onScope(ev.target.value as AccountScope)}>
        <FormControlLabel
          value="all"
          control={<Radio inputProps={{ 'data-testid': allId } as InputHTMLAttributes<HTMLInputElement>} />}
          label="All accounts in this tenant"
        />
        <FormControlLabel
          value="selected"
          control={<Radio inputProps={{ 'data-testid': selectedId } as InputHTMLAttributes<HTMLInputElement>} />}
          label="Selected accounts"
        />
      </RadioGroup>
      {scope === 'selected' ? (
        <Stack spacing={1}>
          <TextField
            label="Find an account"
            value={query}
            onChange={(ev) => onQuery(ev.target.value)}
            inputProps={{ 'data-testid': scopeTestId === 'edit' ? 'users-account-search' : 'users-create-account-search' }}
          />
          {options.map((account) => (
            <FormControlLabel
              key={account.id}
              control={
                <Checkbox
                  checked={selectedIds.includes(account.id)}
                  onChange={(ev) => onToggle(account.id, account.name, ev.target.checked)}
                  inputProps={{ 'data-testid': `users-account-option-${account.id}` } as InputHTMLAttributes<HTMLInputElement>}
                />
              }
              label={account.name}
            />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}

export function UsersWorkspace() {
  const qc = useQueryClient();
  const { data: me, isError: meError, isPending: mePending } = useCurrentUser();
  const isAdmin = String(me?.role || '').toLowerCase() === 'admin';

  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<UserRole>('viewer');
  const [formError, setFormError] = useState<string | null>(null);
  const [formOk, setFormOk] = useState<string | null>(null);
  const [accessUserId, setAccessUserId] = useState('');
  const [accessMode, setAccessMode] = useState<Record<string, 'none' | 'read' | 'edit'>>({});
  const [grainDraft, setGrainDraft] = useState('product_line');
  const [createScope, setCreateScope] = useState<AccountScope>('all');
  const [createAccountIds, setCreateAccountIds] = useState<number[]>([]);
  const [accountUserId, setAccountUserId] = useState('');
  const [editScope, setEditScope] = useState<AccountScope>('all');
  const [editAccountIds, setEditAccountIds] = useState<number[]>([]);
  const [accountQuery, setAccountQuery] = useState('');
  const [accountQueryDebounced, setAccountQueryDebounced] = useState('');
  const [knownAccounts, setKnownAccounts] = useState<Record<number, string>>({});
  const hydratedAccountUser = useRef('');

  const usersQuery = useQuery({
    queryKey: ['auth', 'users'],
    queryFn: () => apiGet<UsersResponse>('/api/v1/auth/users'),
    enabled: isAdmin,
    retry: false,
  });

  const linesQuery = useQuery({
    queryKey: ['auth', 'product-lines'],
    queryFn: () => apiGet<{ product_lines?: string[] }>('/api/v1/auth/product-lines'),
    enabled: isAdmin,
    retry: false,
  });

  const grainQuery = useQuery({
    queryKey: ['auth', 'column-grain'],
    queryFn: () => apiGet<{ grain?: string }>('/api/v1/auth/column-grain'),
    enabled: isAdmin,
    retry: false,
  });

  const catalog = useMemo(
    () => (Array.isArray(linesQuery.data?.product_lines) ? linesQuery.data.product_lines : []),
    [linesQuery.data],
  );

  const accessUserIsAdmin = useMemo(
    () =>
      (usersQuery.data?.users ?? []).some(
        (u) => u.id === accessUserId && String(u.role || '').toLowerCase() === 'admin',
      ),
    [usersQuery.data, accessUserId],
  );

  const accessQuery = useQuery({
    queryKey: ['auth', 'user-product-lines', accessUserId],
    queryFn: () =>
      apiGet<{ assignments?: { product_line: string; can_edit: boolean }[] }>(
        `/api/v1/auth/users/${accessUserId}/product-lines`,
      ),
    enabled: isAdmin && accessUserId !== '',
    retry: false,
  });

  const searchAccounts = isAdmin && (createScope === 'selected' || editScope === 'selected');
  const accountSearchQuery = useQuery({
    queryKey: ['auth', 'customer-accounts', accountQueryDebounced],
    queryFn: () =>
      apiGet<{ accounts?: AccountChoice[] }>(
        `/api/v1/auth/customer-accounts?q=${encodeURIComponent(accountQueryDebounced)}`,
      ),
    enabled: searchAccounts,
    retry: false,
  });
  const userAccountsQuery = useQuery({
    queryKey: ['auth', 'user-accounts', accountUserId],
    queryFn: () =>
      apiGet<{ account_scope?: AccountScope; customer_ids?: number[]; accounts?: AccountChoice[] }>(
        `/api/v1/auth/users/${accountUserId}/accounts`,
      ),
    enabled: isAdmin && accountUserId !== '',
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      apiPost<ListedUser>('/api/v1/auth/users', {
        email,
        display_name: displayName,
        role,
        tenant_id: me?.tenant_id || 'default',
        account_scope: createScope,
        customer_ids: createScope === 'selected' ? createAccountIds : [],
      }),
    onSuccess: async (created) => {
      setFormError(null);
      setFormOk(
        created.invite_sent
          ? `Invite sent to ${created.email}. They choose a password from the link.`
          : `Created ${created.email}. The invite email did not send. Use Resend invite.`,
      );
      setEmail('');
      setDisplayName('');
      setRole('viewer');
      setCreateScope('all');
      setCreateAccountIds([]);
      await qc.invalidateQueries({ queryKey: ['auth', 'users'] });
    },
    onError: (err) => {
      setFormOk(null);
      setFormError(safeDisplayError(err));
    },
  });

  useEffect(() => {
    if (grainQuery.data?.grain) setGrainDraft(grainQuery.data.grain);
  }, [grainQuery.data?.grain]);

  useEffect(() => {
    const timer = window.setTimeout(() => setAccountQueryDebounced(accountQuery), 300);
    return () => window.clearTimeout(timer);
  }, [accountQuery]);

  useEffect(() => {
    const found = accountSearchQuery.data?.accounts ?? [];
    if (!found.length) return;
    setKnownAccounts((prev) => {
      const next = { ...prev };
      for (const account of found) next[account.id] = account.name;
      return next;
    });
  }, [accountSearchQuery.data]);

  useEffect(() => {
    if (!accountUserId) {
      hydratedAccountUser.current = '';
      return;
    }
    const data = userAccountsQuery.data;
    if (!data || hydratedAccountUser.current === accountUserId) return;
    hydratedAccountUser.current = accountUserId;
    const ids = Array.isArray(data.customer_ids) ? data.customer_ids : [];
    setEditScope(data.account_scope === 'selected' && ids.length > 0 ? 'selected' : 'all');
    setEditAccountIds(ids);
    const named = data.accounts ?? [];
    if (!named.length) return;
    setKnownAccounts((prev) => {
      const next = { ...prev };
      for (const account of named) next[account.id] = account.name;
      return next;
    });
  }, [accountUserId, userAccountsQuery.data]);

  useEffect(() => {
    const next: Record<string, 'none' | 'read' | 'edit'> = {};
    for (const line of catalog) next[line] = 'none';
    for (const row of accessQuery.data?.assignments ?? []) {
      const line = String(row.product_line || '').trim();
      if (!line) continue;
      next[line] = row.can_edit ? 'edit' : 'read';
    }
    setAccessMode(next);
  }, [catalog, accessQuery.data]);

  const saveAccess = useMutation({
    mutationFn: () =>
      apiPut(`/api/v1/auth/users/${accessUserId}/product-lines`, {
        assignments: Object.entries(accessMode)
          .filter(([, mode]) => mode !== 'none')
          .map(([product_line, mode]) => ({ product_line, can_edit: mode === 'edit' })),
      }),
    onSuccess: async () => {
      setFormError(null);
      setFormOk('Product line access saved');
      await qc.invalidateQueries({ queryKey: ['auth', 'user-product-lines', accessUserId] });
    },
    onError: (err) => {
      setFormOk(null);
      setFormError(safeDisplayError(err));
    },
  });

  const saveGrain = useMutation({
    mutationFn: () => apiPut('/api/v1/auth/column-grain', { grain: grainDraft.trim() || 'product_line' }),
    onSuccess: async () => {
      setFormError(null);
      setFormOk('Column mapping grain saved');
      await qc.invalidateQueries({ queryKey: ['auth', 'column-grain'] });
    },
    onError: (err) => {
      setFormOk(null);
      setFormError(safeDisplayError(err));
    },
  });

  const saveAccounts = useMutation({
    mutationFn: () =>
      apiPut(`/api/v1/auth/users/${accountUserId}/accounts`, {
        account_scope: editScope,
        customer_ids: editScope === 'selected' ? editAccountIds : [],
      }),
    onSuccess: async () => {
      setFormError(null);
      setFormOk('Customer accounts saved. My accounts turns on at the next sign-in.');
      await qc.invalidateQueries({ queryKey: ['auth', 'user-accounts', accountUserId] });
    },
    onError: (err) => {
      setFormOk(null);
      setFormError(safeDisplayError(err));
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormOk(null);
    if (createScope === 'selected' && createAccountIds.length === 0) {
      setFormError('Choose all accounts in this tenant, or at least one account.');
      return;
    }
    createMutation.mutate();
  }

  const resetPassword = useCallback((u: ListedUser) => {
    const next = window.prompt(`New password for ${u.email} (min 8 chars)`);
    if (!next || next.length < 8) {
      if (next != null) setFormError('Password must be at least 8 characters');
      return;
    }
    setFormError(null);
    setFormOk(null);
    apiPost(`/api/v1/auth/users/${u.id}/set-password`, {
      new_password: next,
      revoke_sessions: true,
    })
      .then(() => {
        setFormOk(`Password reset for ${u.email}`);
      })
      .catch((err) => setFormError(safeDisplayError(err)));
  }, []);

  const resendInvite = useCallback((u: ListedUser) => {
    setFormError(null);
    setFormOk(null);
    apiPost<{ invite_sent?: boolean }>(`/api/v1/auth/users/${u.id}/invite`)
      .then((res) => {
        setFormOk(
          res.invite_sent
            ? `Invite sent to ${u.email}. The previous link no longer works.`
            : `The invite email to ${u.email} did not send.`,
        );
      })
      .catch((err) => setFormError(safeDisplayError(err)));
  }, []);

  const userColDefs = useMemo<ColDef<ListedUser>[]>(
    () => [
      { field: 'email', headerName: 'Email', flex: 1, minWidth: 180 },
      { field: 'display_name', headerName: 'Name', flex: 1, minWidth: 140 },
      { field: 'role', headerName: 'Role', minWidth: 110 },
      {
        field: 'is_active',
        headerName: 'Active',
        minWidth: 90,
        valueFormatter: (p) => (p.value ? 'yes' : 'no'),
      },
      {
        headerName: 'Actions',
        minWidth: 280,
        sortable: false,
        filter: false,
        cellRenderer: (p: { data?: ListedUser }) =>
          p.data ? (
            <Stack direction="row" spacing={1}>
              <Button size="small" data-testid={`users-resend-invite-${p.data.id}`} onClick={() => resendInvite(p.data!)}>
                Resend invite
              </Button>
              <Button size="small" data-testid={`users-reset-password-${p.data.id}`} onClick={() => resetPassword(p.data!)}>
                Reset password
              </Button>
            </Stack>
          ) : null,
      },
    ],
    [resetPassword, resendInvite],
  );

  const accountOptions = useMemo(() => {
    const byId = new Map<number, AccountChoice>();
    for (const account of accountSearchQuery.data?.accounts ?? []) byId.set(account.id, account);
    for (const id of [...createAccountIds, ...editAccountIds]) {
      if (!byId.has(id)) byId.set(id, { id, name: knownAccounts[id] || `Account ${id}` });
    }
    return [...byId.values()];
  }, [accountSearchQuery.data, createAccountIds, editAccountIds, knownAccounts]);

  function toggleIds(
    current: number[],
    setIds: (ids: number[]) => void,
    id: number,
    name: string,
    checked: boolean,
  ) {
    setKnownAccounts((prev) => ({ ...prev, [id]: name }));
    setIds(checked ? [...current.filter((item) => item !== id), id] : current.filter((item) => item !== id));
  }

  if (mePending && !me && !meError) {
    return (
      <Box data-testid="users-workspace">
        <Typography color="text.secondary" data-testid="users-auth-loading">
          Checking access…
        </Typography>
      </Box>
    );
  }

  if (meError || !isAdmin) {
    return (
      <Box data-testid="users-workspace">
        <Alert severity="warning" data-testid="users-forbidden">
          Admin role required to manage users.
        </Alert>
      </Box>
    );
  }

  return (
    <Box data-testid="users-workspace">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Add accounts for this tenant. Roles: admin, steward, planner, viewer. A new person gets an email
        with a link to choose their password. The link works once and expires in 72 hours. The email does
        not contain a password.
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }} component="form" onSubmit={onSubmit} data-testid="users-create-form">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Create user
        </Typography>
        <Stack spacing={2} maxWidth={480}>
          {formError ? (
            <Alert severity="error" data-testid="users-create-error">
              {formError}
            </Alert>
          ) : null}
          {formOk ? (
            <Alert severity="success" data-testid="users-create-ok">
              {formOk}
            </Alert>
          ) : null}
          <TextField
            label="Email"
            type="email"
            required
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            inputProps={{ 'data-testid': 'users-email' }}
          />
          <TextField
            label="Display name"
            required
            value={displayName}
            onChange={(ev) => setDisplayName(ev.target.value)}
            inputProps={{ 'data-testid': 'users-display-name' }}
          />
          <FormControl fullWidth>
            <InputLabel id="users-role-label">Role</InputLabel>
            <Select
              labelId="users-role-label"
              label="Role"
              value={role}
              onChange={(ev) => setRole(ev.target.value as UserRole)}
              inputProps={{ 'data-testid': 'users-role' }}
            >
              {ROLES.map((r) => (
                <MenuItem key={r} value={r}>
                  {r}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <AccountScopeControls
            scope={createScope}
            onScope={setCreateScope}
            selectedIds={createAccountIds}
            onToggle={(id, name, checked) => toggleIds(createAccountIds, setCreateAccountIds, id, name, checked)}
            query={accountQuery}
            onQuery={setAccountQuery}
            options={accountOptions}
            scopeTestId="create"
          />
          <Box>
            <Button
              type="submit"
              variant="contained"
              disabled={createMutation.isPending}
              data-testid="users-create-submit"
            >
              {createMutation.isPending ? 'Sending invite…' : 'Create and send invite'}
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }} data-testid="users-account-editor">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Customer accounts
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="users-account-note">
          {ACCOUNT_EMPTY_NOTE}
        </Typography>
        <Stack spacing={2} maxWidth={640}>
          <FormControl fullWidth>
            <InputLabel id="users-account-user-label">User</InputLabel>
            <Select
              labelId="users-account-user-label"
              label="User"
              value={accountUserId}
              onChange={(ev) => setAccountUserId(String(ev.target.value))}
              inputProps={{ 'data-testid': 'users-account-user' }}
            >
              {(usersQuery.data?.users ?? []).map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.display_name || u.email}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <AccountScopeControls
            scope={editScope}
            onScope={setEditScope}
            selectedIds={editAccountIds}
            onToggle={(id, name, checked) => toggleIds(editAccountIds, setEditAccountIds, id, name, checked)}
            query={accountQuery}
            onQuery={setAccountQuery}
            options={accountOptions}
            scopeTestId="edit"
          />
          <Box>
            <Button
              variant="contained"
              disabled={!accountUserId || saveAccounts.isPending}
              data-testid="users-account-save"
              onClick={() => {
                setFormError(null);
                setFormOk(null);
                if (editScope === 'selected' && editAccountIds.length === 0) {
                  setFormError('Choose all accounts in this tenant, or at least one account.');
                  return;
                }
                saveAccounts.mutate();
              }}
            >
              {saveAccounts.isPending ? 'Saving…' : 'Save customer accounts'}
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }} data-testid="product-line-access">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Product line access
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Each person sees only the product lines assigned here. Read shows the data. Edit allows changes. Someone with no lines sees no product data. Admins see and edit every product line without an assignment.
        </Typography>
        <Stack spacing={2} maxWidth={640}>
          <FormControl fullWidth>
            <InputLabel id="product-line-user-label">User</InputLabel>
            <Select
              labelId="product-line-user-label"
              label="User"
              value={accessUserId}
              onChange={(ev) => setAccessUserId(String(ev.target.value))}
              inputProps={{ 'data-testid': 'product-line-user' }}
            >
              {(usersQuery.data?.users ?? []).map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.email}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {accessUserIsAdmin ? (
            <Typography variant="body2" color="text.secondary" data-testid="product-line-admin-note">
              This person is an admin and sees every product line. Lines saved here apply only if their role changes.
            </Typography>
          ) : null}
          {catalog.length === 0 ? (
            <Typography color="text.secondary" data-testid="product-line-empty">
              No product lines on the master yet.
            </Typography>
          ) : (
            catalog.map((line) => (
              <FormControl key={line} fullWidth>
                <InputLabel id={`product-line-mode-${line}`}>{line}</InputLabel>
                <Select
                  labelId={`product-line-mode-${line}`}
                  label={line}
                  value={accessMode[line] ?? 'none'}
                  onChange={(ev) =>
                    setAccessMode((prev) => ({
                      ...prev,
                      [line]: ev.target.value as 'none' | 'read' | 'edit',
                    }))
                  }
                  inputProps={{ 'data-testid': `product-line-mode-${line}` }}
                >
                  <MenuItem value="none">No access</MenuItem>
                  <MenuItem value="read">Read</MenuItem>
                  <MenuItem value="edit">Read and edit</MenuItem>
                </Select>
              </FormControl>
            ))
          )}
          <Box>
            <Button
              variant="contained"
              disabled={!accessUserId || saveAccess.isPending}
              data-testid="product-line-save"
              onClick={() => saveAccess.mutate()}
            >
              {saveAccess.isPending ? 'Saving…' : 'Save product line access'}
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }} data-testid="column-grain">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Column mapping grain
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This business maps columns by product line. A super user can set a different grain for another business. Product catalog rows stay in place.
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center" maxWidth={480}>
          <TextField
            label="Grain"
            value={grainDraft}
            onChange={(ev) => setGrainDraft(ev.target.value)}
            inputProps={{ 'data-testid': 'column-grain-input' }}
          />
          <Button
            variant="contained"
            disabled={saveGrain.isPending || grainDraft.trim() === ''}
            data-testid="column-grain-save"
            onClick={() => saveGrain.mutate()}
          >
            {saveGrain.isPending ? 'Saving…' : 'Save grain'}
          </Button>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }} data-testid="users-table">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Tenant users
        </Typography>
        <ModuleDataSection
          isLoading={usersQuery.isPending}
          isError={usersQuery.isError}
          error={usersQuery.isError ? new Error(safeDisplayError(usersQuery.error)) : null}
          onRetry={() => void usersQuery.refetch()}
          isEmpty={(usersQuery.data?.users?.length ?? 0) === 0}
          empty={{
            title: 'No users yet',
            description: 'Create the first tenant user with the form above.',
          }}
        >
          <EnterpriseDataGrid rowData={usersQuery.data?.users ?? []} columnDefs={userColDefs} height={360} />
        </ModuleDataSection>
      </Paper>
    </Box>
  );
}

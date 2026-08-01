'use client';

import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';
import type { UserRole } from '@cip/types';

import { PageHeader } from '@/components/PageHeader';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type ListedUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  tenant_id: string;
  is_active: boolean;
};

type UsersResponse = {
  tenant_id: string;
  users: ListedUser[];
};

const ROLES: UserRole[] = ['admin', 'steward', 'planner', 'viewer'];

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const { data: me, isError: meError } = useCurrentUser();
  const isAdmin = String(me?.role || '').toLowerCase() === 'admin';

  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('viewer');
  const [formError, setFormError] = useState<string | null>(null);
  const [formOk, setFormOk] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: ['auth', 'users'],
    queryFn: () => apiGet<UsersResponse>('/api/v1/auth/users'),
    enabled: isAdmin,
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      apiPost<ListedUser>('/api/v1/auth/users', {
        email,
        password,
        display_name: displayName,
        role,
        tenant_id: me?.tenant_id || 'default',
      }),
    onSuccess: async (created) => {
      setFormError(null);
      setFormOk(`Created ${created.email} (${created.role})`);
      setEmail('');
      setDisplayName('');
      setPassword('');
      setRole('viewer');
      await qc.invalidateQueries({ queryKey: ['auth', 'users'] });
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
    createMutation.mutate();
  }

  if (meError || (me && !isAdmin)) {
    return (
      <>
        <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Users' }]} title="Users" />
        <Alert severity="warning" data-testid="users-forbidden">
          Admin role required to manage users.
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Users' }]} title="Users" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Add accounts for this tenant. Roles: admin, steward, planner, viewer.
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
          <TextField
            label="Temporary password"
            type="password"
            required
            helperText="Minimum 8 characters"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            inputProps={{ 'data-testid': 'users-password', minLength: 8 }}
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
          <Box>
            <Button
              type="submit"
              variant="contained"
              disabled={createMutation.isPending}
              data-testid="users-create-submit"
            >
              {createMutation.isPending ? 'Creating…' : 'Create user'}
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }} data-testid="users-table">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Tenant users
        </Typography>
        {usersQuery.isError ? (
          <Alert severity="error">{safeDisplayError(usersQuery.error)}</Alert>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Email</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Active</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(usersQuery.data?.users ?? []).map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>{u.display_name}</TableCell>
                  <TableCell>{u.role}</TableCell>
                  <TableCell>{u.is_active ? 'yes' : 'no'}</TableCell>
                </TableRow>
              ))}
              {!usersQuery.isLoading && (usersQuery.data?.users?.length ?? 0) === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>No users yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
      </Paper>
    </>
  );
}

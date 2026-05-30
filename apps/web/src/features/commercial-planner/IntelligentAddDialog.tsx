'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';
import { EntitySearchAutocomplete } from './EntitySearchAutocomplete';

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };

type RankingRow = {
  product_id: number;
  sku: string;
  product_name: string;
  opportunity_score: number;
  confidence: string;
  trust_tier: string;
  already_in_plan: boolean;
  suggested_target_units: number;
  suggested_srp_local?: number;
};

type RankingsResponse = {
  items: RankingRow[];
};

export type IntelligentAddDialogProps = {
  open: boolean;
  onClose: () => void;
  activePlanId: number | null;
  onCreated: () => void;
  existingLineKeys: Set<string>;
};

export function IntelligentAddDialog({
  open,
  onClose,
  activePlanId,
  onCreated,
  existingLineKeys,
}: IntelligentAddDialogProps) {
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  const [distributor, setDistributor] = useState<DistributorPick | null>(null);
  const [rankings, setRankings] = useState<RankingRow[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);

  const reset = () => {
    setCustomer(null);
    setDistributor(null);
    setRankings([]);
    setSelected(new Set());
    setError(null);
    setSummary(null);
    setLoading(false);
    setCreating(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const loadRankings = async () => {
    if (!activePlanId || !customer || !distributor) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<RankingsResponse>(
        `/api/v1/commercial-planner/plans/${activePlanId}/intelligence/customer/${customer.id}/product-rankings?distributor_id=${distributor.id}&limit=50`,
      );
      setRankings(res.items);
      setSelected(new Set(res.items.filter((r) => !r.already_in_plan).slice(0, 10).map((r) => r.product_id)));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load rankings');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!activePlanId || !customer || !distributor) return;
    setCreating(true);
    setError(null);
    let created = 0;
    let skipped = 0;
    for (const row of rankings) {
      if (!selected.has(row.product_id)) continue;
      const key = `${customer.id}|${distributor.id}|${row.product_id}`;
      if (existingLineKeys.has(key)) {
        skipped++;
        continue;
      }
      try {
        await apiPost(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, {
          customer_id: customer.id,
          distributor_id: distributor.id,
          product_id: row.product_id,
          target_units: row.suggested_target_units,
          target_srp_local:
            row.suggested_srp_local != null && row.suggested_srp_local > 0
              ? row.suggested_srp_local
              : 1000,
          promo_mix_pct: 0.5,
        });
        created++;
      } catch {
        skipped++;
      }
    }
    setSummary(
      `Created ${created} line(s). Skipped or failed: ${skipped}. Review SRP in the grid and recalculate.`,
    );
    setCreating(false);
    if (created > 0) onCreated();
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="lg">
      <DialogTitle>Intelligent add — ranked products</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Pick customer and distributor, load ranked products from sell-out, forecast, lineup evidence, and
            economics. Select rows to add — then set prices in the grid and recalculate.
          </Typography>
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={customer}
            onChange={setCustomer}
            fetchOptions={async (q, signal) => {
              const res = await apiGet<{ items: CustomerPick[] }>(
                `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                { signal },
              );
              return res.items;
            }}
            getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
          />
          <EntitySearchAutocomplete<DistributorPick>
            label="Distributor"
            value={distributor}
            onChange={setDistributor}
            fetchOptions={async (q, signal) => {
              const res = await apiGet<{ items: DistributorPick[] }>(
                `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                { signal },
              );
              return res.items;
            }}
            getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
          />
          <Button
            variant="outlined"
            onClick={() => void loadRankings()}
            disabled={!customer || !distributor || loading}
            data-testid="load-product-rankings-btn"
          >
            {loading ? 'Loading…' : 'Load rankings'}
          </Button>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {rankings.length > 0 ? (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>SKU</TableCell>
                    <TableCell>Product</TableCell>
                    <TableCell align="right">Score</TableCell>
                    <TableCell>Trust</TableCell>
                    <TableCell align="right">Sug. units</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rankings.map((r) => (
                    <TableRow key={r.product_id}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={selected.has(r.product_id)}
                          disabled={r.already_in_plan}
                          onChange={(e) => {
                            setSelected((prev) => {
                              const next = new Set(prev);
                              if (e.target.checked) next.add(r.product_id);
                              else next.delete(r.product_id);
                              return next;
                            });
                          }}
                        />
                      </TableCell>
                      <TableCell>{r.sku}</TableCell>
                      <TableCell>{r.product_name}</TableCell>
                      <TableCell align="right">{r.opportunity_score}</TableCell>
                      <TableCell>{r.trust_tier}</TableCell>
                      <TableCell align="right">{r.suggested_target_units}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : null}
          {summary ? <Alert severity="info">{summary}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Close</Button>
        <Button
          variant="contained"
          disabled={creating || selected.size === 0}
          onClick={() => void handleCreate()}
          data-testid="intelligent-add-create-btn"
        >
          Add selected to plan
        </Button>
      </DialogActions>
    </Dialog>
  );
}

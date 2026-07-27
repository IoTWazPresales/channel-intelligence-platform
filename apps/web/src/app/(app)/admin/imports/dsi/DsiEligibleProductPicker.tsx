'use client';

import {
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';

export type DsiEligibleProductSnapshot = {
  product_id: number;
  sku?: string | null;
  part_number?: string | null;
  sales_model_name?: string | null;
  is_active?: boolean;
  lifecycle_status?: string | null;
};

export function DsiEligibleProductPicker({
  tier,
  products,
  selectedProductId,
  onSelectProductId,
  disabled,
}: {
  tier?: string | null;
  products: DsiEligibleProductSnapshot[];
  selectedProductId: number | '';
  onSelectProductId: (id: number | '') => void;
  disabled?: boolean;
}) {
  if (!products.length) return null;

  return (
    <Stack spacing={1.5} data-testid="dsi-eligible-product-picker">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary">
          Multiple eligible Product Master rows — choose one to resolve
        </Typography>
        {tier ? <Chip size="small" variant="outlined" label={`Tier: ${tier}`} /> : null}
      </Stack>
      <FormControl size="small" fullWidth>
        <InputLabel id="dsi-eligible-product-select-label">Product</InputLabel>
        <Select
          labelId="dsi-eligible-product-select-label"
          label="Product"
          value={selectedProductId === '' ? '' : String(selectedProductId)}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            onSelectProductId(v === '' ? '' : Number(v));
          }}
          data-testid="dsi-eligible-product-select"
        >
          <MenuItem value="">
            <em>Select product…</em>
          </MenuItem>
          {products.map((p) => (
            <MenuItem key={p.product_id} value={String(p.product_id)}>
              {formatEligibleProductLabel(p)}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <Table size="small" data-testid="dsi-eligible-product-table">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>SKU</TableCell>
            <TableCell>Part / model</TableCell>
            <TableCell>Lifecycle</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {products.map((p) => (
            <TableRow
              key={p.product_id}
              hover
              selected={selectedProductId !== '' && selectedProductId === p.product_id}
              sx={{ cursor: disabled ? 'default' : 'pointer' }}
              onClick={() => {
                if (!disabled) onSelectProductId(p.product_id);
              }}
            >
              <TableCell>{p.product_id}</TableCell>
              <TableCell>{p.sku || '—'}</TableCell>
              <TableCell>
                {[p.part_number, p.sales_model_name].filter(Boolean).join(' · ') || '—'}
              </TableCell>
              <TableCell>
                {p.lifecycle_status || (p.is_active === false ? 'inactive' : 'active')}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Stack>
  );
}

function formatEligibleProductLabel(p: DsiEligibleProductSnapshot): string {
  const sku = (p.sku || '').trim();
  const model = (p.sales_model_name || p.part_number || '').trim();
  const base = sku || model || `id ${p.product_id}`;
  return model && sku ? `${sku} — ${model}` : base;
}

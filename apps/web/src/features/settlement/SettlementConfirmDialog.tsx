'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import { CporSettleReadinessRow } from '@/features/cpor/CporSettleReadinessRow';
import { formatLocalMoney, type SettleReadiness } from '@/features/cpor/fxDisplay';

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  confirming?: boolean;
  caseCode: string;
  customerLabel: string;
  periodLabel?: string;
  outstandingAmount: number | null | undefined;
  currencyCode?: string;
  settleReadiness?: SettleReadiness;
  claimRowCount?: number;
  unresolvedProductCount?: number;
};

export function SettlementConfirmDialog({
  open,
  onClose,
  onConfirm,
  confirming,
  caseCode,
  customerLabel,
  periodLabel,
  outstandingAmount,
  currencyCode = 'ZAR',
  settleReadiness,
  claimRowCount = 0,
  unresolvedProductCount = 0,
}: Props) {
  const theme = useTheme();
  const fxBlocked = settleReadiness?.fx_settle_allowed === false;
  const amountLabel = formatLocalMoney(outstandingAmount ?? null, currencyCode);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="settlement-confirm-dialog">
      <DialogTitle>Record settlement?</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Case <strong>{caseCode}</strong> · {customerLabel}
          {periodLabel ? ` · ${periodLabel}` : ''}
        </Typography>
        <Typography
          sx={{
            fontSize: '9.5px',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: alpha(theme.palette.text.primary, 0.45),
          }}
        >
          Outstanding
        </Typography>
        <Typography
          data-testid="settlement-confirm-amount"
          sx={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: '28px',
            fontWeight: 500,
            my: 1,
          }}
        >
          {amountLabel}
        </Typography>
        {settleReadiness ? (
          <Box sx={{ mb: 1.5 }}>
            <CporSettleReadinessRow readiness={settleReadiness} testIdPrefix="settlement-confirm-readiness" />
          </Box>
        ) : null}
        {claimRowCount === 0 ? (
          <Alert severity="warning" sx={{ mb: 1.5 }} data-testid="settlement-confirm-zero-claims">
            <strong>Zero claim evidence attached.</strong> Settlement will record the case as settled — it does not
            post a payment. CST divergence never blocks settlement.
          </Alert>
        ) : null}
        {unresolvedProductCount > 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Unresolved SKUs stay on the assumptions worklist. Confirm only if you accept settling with open
            assumptions.
          </Typography>
        ) : null}
        {fxBlocked ? (
          <Alert severity="error" data-testid="settlement-confirm-fx-blocked">
            FX basis is not ready — settlement is blocked until rate of exchange is declared and FX mode is valid.
          </Alert>
        ) : (
          <Typography variant="caption" color="text.secondary" display="block">
            Settlement records case status only; it does not post payment. Confirm only if you accept the outstanding
            amount at the declared FX basis.
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={confirming}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={confirming || fxBlocked}
          onClick={onConfirm}
          data-testid="settlement-confirm-submit"
        >
          {confirming ? 'Settling…' : `Confirm settlement · ${amountLabel}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

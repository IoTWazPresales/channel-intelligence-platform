'use client';

import { Button, CircularProgress, type ButtonProps } from '@mui/material';

/** MUI Button with spinner, disabled while pending — prevents double-submit. */
export function DsiPendingButton({
  pending = false,
  pendingLabel,
  children,
  disabled,
  startIcon,
  ...rest
}: ButtonProps & {
  pending?: boolean;
  /** Shown instead of `children` while pending (optional). */
  pendingLabel?: string;
}) {
  const busy = Boolean(pending);
  return (
    <Button
      {...rest}
      disabled={disabled || busy}
      startIcon={busy ? <CircularProgress size={14} color="inherit" /> : startIcon}
    >
      {busy && pendingLabel != null ? pendingLabel : children}
    </Button>
  );
}

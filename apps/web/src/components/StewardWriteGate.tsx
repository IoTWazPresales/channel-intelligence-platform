'use client';

import { Alert } from '@mui/material';
import { styled } from '@mui/material/styles';
import { useId, type ReactNode } from 'react';

import { useStewardWriteAccess, type StewardWriteAccess } from '@/features/shell/stewardAccess';

/**
 * A plain fieldset with no visual chrome. When `disabled`, the browser disables every button, input,
 * select and textarea inside it (MUI buttons, icon buttons, checkboxes and text fields render native
 * elements), so a role without steward access cannot start a write from this area. Dialogs rendered in
 * a portal sit outside the fieldset and must check access themselves.
 */
const BareFieldset = styled('fieldset')({
  border: 0,
  margin: 0,
  padding: 0,
  minWidth: 0,
  '&:disabled :disabled': { cursor: 'not-allowed', opacity: 0.6 },
});

export function StewardWriteNotice({
  access,
  extra,
  id,
}: {
  access: StewardWriteAccess;
  /** One more sentence for this page, e.g. what still works for the role. */
  extra?: ReactNode;
  id?: string;
}) {
  if (access.allowed || !access.reason) return null;
  return (
    <Alert severity="info" sx={{ mb: 2 }} role="status" id={id} data-testid="steward-write-notice">
      <strong>View only for your role.</strong> {access.reason}
      {extra ? <> {extra}</> : null}
    </Alert>
  );
}

/** The fieldset alone, for pages that place the notice themselves. */
export function StewardWriteFieldset({
  disabled,
  describedBy,
  children,
}: {
  disabled: boolean;
  describedBy?: string;
  children: ReactNode;
}) {
  return (
    <BareFieldset
      disabled={disabled}
      aria-disabled={disabled || undefined}
      aria-describedby={disabled ? describedBy : undefined}
      data-testid="steward-write-area"
    >
      {children}
    </BareFieldset>
  );
}

/**
 * Notice plus disabled fieldset for a steward work surface (N-0086). The fieldset is always rendered
 * so the page does not remount when the role arrives; only its `disabled` flag changes.
 */
export function StewardWriteGate({ children, extra }: { children: ReactNode; extra?: ReactNode }) {
  const access = useStewardWriteAccess();
  const noticeId = useId();
  return (
    <>
      <StewardWriteNotice access={access} extra={extra} id={noticeId} />
      <StewardWriteFieldset disabled={!access.allowed} describedBy={noticeId}>
        {children}
      </StewardWriteFieldset>
    </>
  );
}

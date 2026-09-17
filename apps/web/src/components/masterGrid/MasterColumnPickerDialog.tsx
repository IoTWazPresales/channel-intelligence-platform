'use client';

import {
  ColumnPickerDialog,
  type ColumnPickerDialogMdProps,
  type MasterColumnPickerGroup,
} from '@/features/workbench-ui/ColumnPickerDialog';

export type { MasterColumnPickerGroup };

/** Thin host wrapper — implementation lives in workbench-ui ColumnPickerDialog (size=md). */
export function MasterColumnPickerDialog(props: Omit<ColumnPickerDialogMdProps, 'size'>) {
  return <ColumnPickerDialog size="md" {...props} />;
}

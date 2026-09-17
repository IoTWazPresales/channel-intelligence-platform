'use client';

import {
  ColumnPickerDialog,
  type ColumnMetadata,
  type ColumnSelectorModalProps,
} from '@/features/workbench-ui/ColumnPickerDialog';

export type { ColumnMetadata, ColumnSelectorModalProps };

/** Thin host wrapper — implementation lives in workbench-ui ColumnPickerDialog (size=wide). */
export function ColumnSelectorModal(props: ColumnSelectorModalProps) {
  return <ColumnPickerDialog size="wide" {...props} />;
}

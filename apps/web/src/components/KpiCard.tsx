import { Card, CardContent, Typography } from '@mui/material';
import { ReactNode } from 'react';

export function KpiCard({
  label,
  value,
  hint,
  onExplain,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  onExplain?: () => void;
}) {
  return (
    <Card
      sx={{ height: '100%', cursor: onExplain ? 'pointer' : 'default' }}
      onClick={onExplain}
      role={onExplain ? 'button' : undefined}
    >
      <CardContent>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 600 }}>
          {value}
        </Typography>
        {hint ? (
          <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 1 }}>
            {hint}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  );
}

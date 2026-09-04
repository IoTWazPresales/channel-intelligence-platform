'use client';

import {
  Box,
  Link,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Step,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import HubOutlinedIcon from '@mui/icons-material/HubOutlined';
import TableChartOutlinedIcon from '@mui/icons-material/TableChartOutlined';
import NextLink from 'next/link';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';

const steps = ['Sign in', 'Bring data in', 'Map & steward', 'Use planning views'];

/** Legacy /getting-started route — middleware redirects to /brief; thin fallback if middleware is bypassed. */
export default function GettingStartedPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/brief', { extraCrumbs: [{ label: 'Onboarding' }] })} />
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 720 }}>
        Sign in with your CIP account (session auth). Admins create users under{' '}
        <Link component={NextLink} href="/admin/users" fontWeight={600}>
          Administration → Users & roles
        </Link>
        . Nav is role-gated (admin / steward / planner / viewer). After login you land on{' '}
        <Link component={NextLink} href="/brief" fontWeight={600}>
          Attention
        </Link>
        .
      </Typography>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Stepper activeStep={0} alternativeLabel sx={{ mb: 2 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        <Typography variant="subtitle2" color="text.secondary">
          You can jump to any step; the UI does not block you. Empty modules show a short “what to do next” panel when
          there is no data.
        </Typography>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Recommended path
        </Typography>
        <List>
          <ListItem alignItems="flex-start" sx={{ py: 1.5 }}>
            <ListItemIcon>
              <CloudUploadOutlinedIcon color="primary" />
            </ListItemIcon>
            <ListItemText
              primary="1. Upload a file"
              secondary={
                <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                  Go to{' '}
                  <Link component={NextLink} href="/admin/imports" fontWeight={600}>
                    Data & Stewardship → Import Center
                  </Link>
                  . Pick a <strong>source</strong> (defines expected columns), then use <strong>Choose file</strong> or
                  drag a CSV/XLSX into the drop zone. The API stores the file, infers columns, applies the source
                  mapping, and validates rows.
                </Box>
              }
              primaryTypographyProps={{ variant: 'subtitle1', fontWeight: 600 }}
            />
          </ListItem>
          <ListItem alignItems="flex-start" sx={{ py: 1.5 }}>
            <ListItemIcon>
              <HubOutlinedIcon color="primary" />
            </ListItemIcon>
            <ListItemText
              primary="2. Fix mapping gaps"
              secondary={
                <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                  Open the import job steward panel (DSI / shipment / CST) or{' '}
                  <Link component={NextLink} href="/admin/mappings" fontWeight={600}>
                    Data & Stewardship → Steward queue
                  </Link>{' '}
                  to approve or correct entity links. Steward decisions are audited under{' '}
                  <Link component={NextLink} href="/admin/steward-audit" fontWeight={600}>
                    Steward audit
                  </Link>
                  .
                </Box>
              }
              primaryTypographyProps={{ variant: 'subtitle1', fontWeight: 600 }}
            />
          </ListItem>
          <ListItem alignItems="flex-start" sx={{ py: 1.5 }}>
            <ListItemIcon>
              <TableChartOutlinedIcon color="primary" />
            </ListItemIcon>
            <ListItemText
              primary="3. Explore capability domains"
              secondary={
                <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                  From Attention, open{' '}
                  <Link component={NextLink} href="/commercial-planner/cpor-cases" fontWeight={600}>
                    Case book
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/stock?lens=movement" fontWeight={600}>
                    Movement
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/stock?lens=inbound" fontWeight={600}>
                    Shipments
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/forecasts" fontWeight={600}>
                    Forecasts
                  </Link>
                  , or{' '}
                  <Link component={NextLink} href="/lineup" fontWeight={600}>
                    Lineup cases
                  </Link>
                  .
                </Box>
              }
              primaryTypographyProps={{ variant: 'subtitle1', fontWeight: 600 }}
            />
          </ListItem>
        </List>
      </Paper>
    </>
  );
}

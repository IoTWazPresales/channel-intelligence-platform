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

const steps = ['Sign in', 'Bring data in', 'Map & steward', 'Use planning views'];

export default function GettingStartedPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Getting started' }]} title="Getting started" />
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 720 }}>
        Sign in with your CIP account (session auth). Admins create users under{' '}
        <Link component={NextLink} href="/admin/users" fontWeight={600}>
          Admin → Users
        </Link>
        . Nav is role-gated (admin / steward / planner / viewer). After login you land on the Control tower with a data
        freshness banner.
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
                    Admin → Import Center
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
                    Admin → Mapping queue
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
              primary="3. Explore planning modules"
              secondary={
                <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                  From the Control tower shortcuts, open{' '}
                  <Link component={NextLink} href="/commercial-planner/cpor-cases" fontWeight={600}>
                    CPOR Cases
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/sell-out" fontWeight={600}>
                    Channel Operations
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/shipping" fontWeight={600}>
                    Inbound shipments
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/forecasts" fontWeight={600}>
                    Forecasting
                  </Link>
                  , or{' '}
                  <Link component={NextLink} href="/lineup" fontWeight={600}>
                    Line-up planning
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

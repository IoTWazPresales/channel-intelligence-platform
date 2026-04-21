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

const steps = ['Bring data in', 'Map columns', 'Review queues', 'Use planning views'];

export default function GettingStartedPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Getting started' }]} title="Getting started" />
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 720 }}>
        This build is an internal MVP: there is no production SSO yet. Use the steps below to load demo or your own
        files, then explore modules. Stub auth sends fixed headers from the web client for now.
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
                    Admin → Data & imports
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
                  Open{' '}
                  <Link component={NextLink} href="/admin/mappings" fontWeight={600}>
                    Admin → Mapping queue
                  </Link>{' '}
                  to approve or correct entity links the pipeline could not infer automatically.
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
                  Open{' '}
                  <Link component={NextLink} href="/inventory" fontWeight={600}>
                    Inventory
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/forecasts" fontWeight={600}>
                    Forecasts
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/buy-plans" fontWeight={600}>
                    Buy plans
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/lineup" fontWeight={600}>
                    Line-up planning
                  </Link>
                  ,{' '}
                  <Link component={NextLink} href="/promotions" fontWeight={600}>
                    Promotions
                  </Link>{' '}
                  (CPOR Excel export & approval on the third tab), and{' '}
                  <Link component={NextLink} href="/budgets" fontWeight={600}>
                    Budgets
                  </Link>
                  . Demo seed data is described in the repo README (Docker on <strong>localhost:8010</strong> for the API).
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

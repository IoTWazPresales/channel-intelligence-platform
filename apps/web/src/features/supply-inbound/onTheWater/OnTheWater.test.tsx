import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ShippingFilterParams } from '@/app/(app)/shipping/buildShippingLinesUrl';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { OnTheWater } from './OnTheWater';
import type { OnTheWaterData, Vessel } from './types';

const hoisted = vi.hoisted(() => ({ body: null as unknown, urls: [] as string[] }));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    hoisted.urls.push(url);
    return hoisted.body;
  }),
  safeDisplayError: (e: unknown) => String(e),
}));
vi.mock('next/link', () => ({ default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => <a href={href} {...rest}>{children}</a> }));

const scope: ShippingFilterParams = {
  lineState: '', cargoStatus: '', distributorId: null, customerId: null, purchaseOrderId: null, search: '', dateField: 'eta_date', dateFrom: '', dateTo: '', productFamily: '',
  productModel: '', currencyCode: '', operatingUnit: '', podDateFilter: '', planQuarter: '', planBusinessUnit: '', lineupAttribution: '', lifecycleBucket: '', slipDirection: '', cohort: '',
};

function vessel(over: Partial<Vessel>): Vessel {
  return {
    id: 'v4', key: 'i:2026-09-19|2026-11-05|ZAJNB|asia_durban', inferred: true, vessel_name: null, forwarder: 'COSCO', lane_id: 'asia_durban',
    lane_label: 'Chongqing / Shenzhen → Durban → City Deep', route_assumed: false, deliver_port: 'ZAJNB', on_board: '2026-09-19', eta: '2026-11-05', days_to_eta: 9, overdue: false,
    days_overdue: 0, pct: 81, units: 4286, lines: 90, deliveries: 26, amount: [{ currency: 'USD', amount: 3_216_610 }],
    distributors: [{ name: 'Rectron', units: 1498 }, { name: 'Mustek', units: 1350 }, { name: 'Pepkor', units: 972 }],
    products: [{ name: 'P1503CVAY', units: 708 }, { name: 'X1504VAP', units: 612 }, { name: 'M1502XA', units: 612 }, { name: 'P1403CVAY', units: 468 }], more_models: 17, slip_days: 0,
    history: { first_eta: '2026-11-05', first_report: '2026-09-29', current_eta: '2026-11-05', latest_report: '2026-10-27' }, x: 46.1, y: 74.86, ...over,
  };
}

function payload(over: Partial<OnTheWaterData> = {}): OnTheWaterData {
  const vessels = [
    vessel({ id: 'v1', key: 'k1', forwarder: 'Premiere', units: 3170, eta: '2026-10-27', x: 33.54, y: 86.18, slip_days: 14, overdue: true, days_overdue: 1, amount: [{ currency: 'USD', amount: 75_365 }], more_models: 3 }),
    vessel({ id: 'v4', key: 'k4', slip_days: 0 }),
    vessel({ id: 'v7', key: 'k7', forwarder: 'WWP', units: 364, eta: '2026-11-25', x: 89.01, y: 36.25, slip_days: 13, more_models: 0, amount: [{ currency: 'USD', amount: 317_694 }] }),
  ];
  return {
    as_of: '2026-10-28', report_date: '2026-10-27', report_age_days: 1, report_stale: false, stale_report_days: 7, reports: { count: 4, earlier: 3, since: '2026-09-29' },
    tiles: {
      at_sea: { units: 15009, lines: 178, vessels: 7, amount: [{ currency: 'USD', amount: 9_220_000 }], air_units: 120, overdue_vessels: 1 },
      arrived: { units: 5512, lines: 40, by_port: [{ name: 'City Deep', units: 5108 }, { name: 'Port Louis', units: 404 }] },
      booked: { units: 851, lines: 34 },
      eta_moved: { vessels_moved: 6, vessels: 7, min_days: 5, max_days: 14, since: '2026-09-29' },
    },
    vessels,
    map: {
      size: [1000, 646],
      lanes: [{ id: 'asia_durban', kind: 'sea', d: 'M 10 10 L 100 100' }, { id: 'durban_city_deep_rail', kind: 'leg', d: 'M 100 100 L 110 110' }],
      ports: [{ id: 'DURBAN', label: 'DURBAN', x: 33.54, y: 86.18 }, { id: 'SHANGHAI', label: 'SHANGHAI', x: 90.82, y: 26.27 }],
      cluster_radius_pct: 4,
    },
    port_rows: [
      { code: 'ZADUR', label: 'Durban', waiting_units: 0, condition: null },
      { code: 'ZAJNB', label: 'City Deep', waiting_units: 5108, condition: { id: 1, port_code: 'ZAJNB', label: 'City Deep', delay_days: 15, note: null, entered_by: 'Warren', entered_at: '2026-10-29T08:00:00+02:00' } },
    ],
    needs_look: { lines: 9, units: 731, distributors: [{ name: 'Pepkor', units: 523 }, { name: 'DCC', units: 130 }], since: '2026-09-29', days: 7, on_board_moved: { from: '2026-10-11', to: '2026-10-18' } },
    position_note: 'estimated',
    ...over,
  };
}

function setup(body: OnTheWaterData | unknown, props: Partial<Parameters<typeof OnTheWater>[0]> = {}) {
  hoisted.body = body;
  hoisted.urls = [];
  const onSelectVessel = vi.fn();
  const onOpenNeedsLook = vi.fn();
  renderWithProviders(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <OnTheWater filterParams={scope} onSelectVessel={onSelectVessel} onOpenNeedsLook={onOpenNeedsLook} byDistributor={<div data-testid="by-distributor">bars</div>} {...props} />
    </QueryClientProvider>,
  );
  return { onSelectVessel, onOpenNeedsLook };
}

describe('OnTheWater', () => {
  it('shows the four tiles with the per-currency value, the air sub-line and the ETA history', async () => {
    setup(payload());
    expect(await screen.findByTestId('otw-tile-at-sea')).toHaveTextContent('15,009');
    expect(screen.getByTestId('otw-tile-at-sea')).toHaveTextContent('US$9.22M · 7 vessels · 178 lines');
    expect(screen.getByTestId('otw-tile-at-sea')).toHaveTextContent('+120 units by air');
    expect(screen.getByTestId('otw-tile-arrived')).toHaveTextContent('City Deep 5,108 · Port Louis 404');
    expect(screen.getByTestId('otw-tile-booked')).toHaveTextContent('34 lines with a future on-board date');
    expect(screen.getByTestId('otw-tile-eta-moved')).toHaveTextContent('ETA moved since 29 Sep');
    expect(screen.getByTestId('otw-tile-eta-moved')).toHaveTextContent('6 of 7');
    expect(screen.getByTestId('otw-tile-eta-moved')).toHaveTextContent('Later by 5 to 14 days · from report history');
    expect(screen.getByText(/compared with 3 earlier reports since 29 Sep/)).toBeInTheDocument();
    expect(screen.getByTestId('otw-data-as-of')).toHaveTextContent('Data as of 27 Oct 2026');
    expect(screen.queryByTestId('otw-stale')).toBeNull();
  });

  it('says the report is old when it is past the tenant threshold', async () => {
    setup(payload({ report_stale: true, report_age_days: 12 }));
    expect(await screen.findByTestId('otw-stale')).toHaveTextContent('Report is 12 days old');
  });

  it('asks the API with the page scope and without the selection filters', async () => {
    setup(payload(), { filterParams: { ...scope, distributorId: 7, vessel: 'k1', cohort: 'needs_look' } });
    await screen.findByTestId('otw-tile-at-sea');
    expect(hoisted.urls).toEqual(['/api/v1/shipping/on-the-water?distributor_id=7&date_field=eta_date']);
  });

  it('toggles between the map and the by-distributor chart', async () => {
    setup(payload());
    await screen.findByTestId('otw-map');
    expect(screen.queryByTestId('by-distributor')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'By distributor' }));
    expect(screen.getByTestId('by-distributor')).toBeInTheDocument();
    expect(screen.queryByTestId('otw-map')).toBeNull();
    expect(screen.getByRole('button', { name: 'By distributor' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Map' }));
    expect(screen.getByTestId('otw-map')).toBeInTheDocument();
  });

  it('shows the hover card on hover and on keyboard focus, with distributors, top products and more models', async () => {
    setup(payload());
    const markers = await screen.findAllByTestId('otw-vessel');
    const v4 = markers.find((m) => m.getAttribute('data-vessel') === 'v4')!;
    expect(v4).toHaveAccessibleName('COSCO, ETA 5 Nov, 4,286 units');
    fireEvent.mouseEnter(v4);
    let card = screen.getByTestId('otw-hover-card');
    expect(card).toHaveAttribute('role', 'tooltip');
    expect(card).toHaveTextContent('ETA 5 Nov · 4,286 u · US$3.22M');
    expect(card).toHaveTextContent('Rectron 1,498 · Mustek 1,350 · Pepkor 972');
    expect(card).toHaveTextContent('P1503CVAY 708 · X1504VAP 612 · M1502XA 612 · P1403CVAY 468');
    expect(card).toHaveTextContent('+17 more models · click to see every line');
    fireEvent.mouseLeave(v4);
    expect(screen.queryByTestId('otw-hover-card')).toBeNull();
    const v7 = markers.find((m) => m.getAttribute('data-vessel') === 'v7')!;
    fireEvent.focus(v7);
    card = screen.getByTestId('otw-hover-card');
    expect(card).toHaveTextContent('Click to see every line');
    fireEvent.blur(v7);
    expect(screen.queryByTestId('otw-hover-card')).toBeNull();
  });

  it('a click on a vessel marker or a list row filters the grid to it; a second click clears it', async () => {
    const { onSelectVessel } = setup(payload());
    const markers = await screen.findAllByTestId('otw-vessel');
    fireEvent.click(markers.find((m) => m.getAttribute('data-vessel') === 'v7')!);
    expect(onSelectVessel).toHaveBeenLastCalledWith('k7');
    const list = screen.getByText('Arriving next').parentElement!;
    fireEvent.click(within(list).getByRole('button', { name: /COSCO/ }));
    expect(onSelectVessel).toHaveBeenLastCalledWith('k4');
  });

  it('marks the selected vessel and shows its panel, slip and ETA history', async () => {
    setup(payload({ vessels: payload().vessels.map((v) => (v.id === 'v1' ? { ...v, slip_days: 14, history: { first_eta: '2026-10-13', first_report: '2026-09-29', current_eta: '2026-10-27', latest_report: '2026-10-27' } } : v)) }), { selectedKey: 'k1' });
    const panel = await screen.findByTestId('otw-selected');
    expect(panel).toHaveTextContent('Selected vessel · inferred');
    expect(panel).toHaveTextContent('ETA +14 days');
    expect(panel).toHaveTextContent('13 Oct on 29 Sep → 27 Oct on 27 Oct');
    expect(panel).toHaveTextContent('Grouped by matching on-board date and ETA');
    const list = screen.getByText('Arriving next').parentElement!;
    expect(within(list).getByRole('button', { name: /Premiere/ })).toHaveAttribute('aria-pressed', 'true');
    expect(within(list).getByRole('button', { name: /WWP/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('lists the ports with their manual figure or "No figure entered · Planned", and links to where it is entered', async () => {
    setup(payload());
    const ports = await screen.findByTestId('otw-ports');
    expect(ports).toHaveTextContent('Durban (ZADUR)');
    expect(ports).toHaveTextContent('No figure entered · Planned');
    expect(ports).toHaveTextContent('City Deep (ZAJNB)');
    expect(ports).toHaveTextContent('5,108 units waiting');
    expect(ports).toHaveTextContent('15 days · entered by Warren, 29 Oct');
    expect(screen.getByTestId('otw-enter-condition')).toHaveAttribute('href', '/admin/port-conditions');
    expect(screen.getByTestId('otw-durban-note')).toHaveTextContent('Durban · No figure entered · Planned');
  });

  it('needs a look: the count, the distributor split and the link that opens the lines', async () => {
    const { onOpenNeedsLook } = setup(payload());
    const card = await screen.findByTestId('otw-needs-look');
    expect(card).toHaveTextContent('9 lines, 731 units, on the Shipped sheet with no ship confirm date since 29 Sep.');
    expect(card).toHaveTextContent('On-board date moved 11 Oct → 18 Oct.');
    expect(card).toHaveTextContent('Pepkor 523 · DCC 130');
    fireEvent.click(screen.getByRole('button', { name: 'Open the 9 lines' }));
    expect(onOpenNeedsLook).toHaveBeenCalledOnce();
  });

  it('has no needs-a-look card when nothing needs one, and pulses at Durban only when a vessel is overdue', async () => {
    setup(payload({ needs_look: null, tiles: { ...payload().tiles, at_sea: { ...payload().tiles.at_sea, overdue_vessels: 0 } } }));
    await screen.findByTestId('otw-map');
    expect(screen.queryByTestId('otw-needs-look')).toBeNull();
    expect(screen.queryByTestId('otw-pulse')).toBeNull();
  });

  it('does not break when the API answers with something else', async () => {
    setup({ reference_date: '2026-10-10', total_lines: 10 });
    expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
    expect(screen.getByTestId('by-distributor')).toBeInTheDocument();
  });
});

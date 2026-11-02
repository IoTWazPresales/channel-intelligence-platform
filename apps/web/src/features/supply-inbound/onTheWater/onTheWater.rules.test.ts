import { describe, expect, it } from 'vitest';

import { buildOnTheWaterUrl, type ShippingFilterParams } from '@/app/(app)/shipping/buildShippingLinesUrl';

import { badgeText, daysText, fmtDay, fmtDayYear, fmtMoney, historyText, nameUnits, slipShort } from './format';
import { clusterChip, clusterVessels, etaRange, labelWidthPx, placeLabels, portsInUse } from './layout';
import type { Vessel } from './types';

function vessel(over: Partial<Vessel> = {}): Vessel {
  return {
    id: 'v1', key: 'i:x', inferred: true, vessel_name: null, forwarder: 'COSCO', lane_id: 'asia_durban', lane_label: 'Chongqing → Durban',
    route_assumed: false, deliver_port: 'ZAJNB', on_board: '2026-09-19', eta: '2026-11-05', days_to_eta: 8, overdue: false, days_overdue: 0, pct: 80,
    units: 100, lines: 2, deliveries: 1, amount: [{ currency: 'USD', amount: 1000 }], distributors: [{ name: 'Mustek', units: 100 }], products: [{ name: 'P1503', units: 100 }],
    more_models: 0, slip_days: 0, history: { first_eta: null, first_report: null, current_eta: '2026-11-05', latest_report: '2026-10-27' }, x: 50, y: 50, ...over,
  };
}

describe('formatting', () => {
  it('dates read as day and month', () => {
    expect(fmtDay('2026-10-27')).toBe('27 Oct');
    expect(fmtDay('2026-11-05T00:00:00')).toBe('5 Nov');
    expect(fmtDayYear('2026-10-27')).toBe('27 Oct 2026');
    expect(fmtDay(null)).toBe('–');
  });

  it('value is per currency and US$ only when every line is USD', () => {
    expect(fmtMoney([{ currency: 'USD', amount: 9_220_000 }])).toBe('US$9.22M');
    expect(fmtMoney([{ currency: 'USD', amount: 784_170 }])).toBe('US$784k');
    expect(fmtMoney([{ currency: 'USD', amount: 850 }])).toBe('US$850');
    expect(fmtMoney([{ currency: 'EUR', amount: 70 }, { currency: 'USD', amount: 140 }])).toBe('EUR 70 · US$140');
    expect(fmtMoney([])).toBe('–');
  });

  it('slip, days and history text', () => {
    expect(slipShort({ slip_days: 14 })).toBe('+14 days');
    expect(slipShort({ slip_days: 1 })).toBe('+1 day');
    expect(slipShort({ slip_days: 0 })).toBe('On time');
    expect(daysText({ days_to_eta: 0, overdue: false, days_overdue: 0 })).toBe('due today');
    expect(daysText({ days_to_eta: 9, overdue: false, days_overdue: 0 })).toBe('in 9 days');
    expect(daysText({ days_to_eta: -8, overdue: true, days_overdue: 8 })).toBe('8 days overdue');
    const moved = vessel({ slip_days: 14, history: { first_eta: '2026-10-22', first_report: '2026-09-29', current_eta: '2026-11-05', latest_report: '2026-10-27' } });
    expect(historyText(moved)).toBe('22 Oct on 29 Sep → 5 Nov on 27 Oct');
    expect(historyText(vessel({ history: { first_eta: '2026-11-05', first_report: '2026-09-29', current_eta: '2026-11-05', latest_report: '2026-10-27' } }))).toBe('5 Nov in every report since 29 Sep');
    expect(nameUnits([{ name: 'Pepkor', units: 523 }, { name: 'DCC', units: 130 }, { name: 'Mustek', units: 57 }], 2)).toBe('Pepkor 523 · DCC 130');
  });
});

describe('clusters and labels', () => {
  it('vessels within the radius collapse into one cluster', () => {
    // The three vessels at or near Durban in the approved mock-up.
    const a = vessel({ id: 'a', x: 33.54, y: 86.18 });
    const b = vessel({ id: 'b', x: 31.2, y: 89.13 });
    const c = vessel({ id: 'c', x: 37.36, y: 84.78 });
    const far = vessel({ id: 'far', x: 80, y: 55 });
    const groups = clusterVessels([a, b, c, far], 4);
    expect(groups.map((g) => g.vessels.map((v) => v.id))).toEqual([['a', 'b', 'c'], ['far']]);
  });

  it('a cluster chip names the nearest port, the units and the ETA range', () => {
    const ports = [{ label: 'DURBAN', x: 33.54, y: 86.18 }, { label: 'SHANGHAI', x: 90, y: 26 }];
    const c = clusterVessels([vessel({ id: 'a', x: 33.5, y: 86.2, units: 3170, eta: '2026-10-27' }), vessel({ id: 'b', x: 31.2, y: 89.1, units: 843, eta: '2026-10-30' })], 4)[0];
    expect(clusterChip(c, ports)).toEqual({ title: '2 vessels at or near Durban', sub: '4,013 u · ETA at port 27–30 Oct' });
    expect(etaRange('2026-10-30', '2026-11-02')).toBe('30 Oct–2 Nov');
  });

  it('labels never overlap each other or leave the map, and the selected vessel is placed first', () => {
    const anchors = [
      { id: 'sel', x: 50, y: 50, priority: 0 },
      { id: 'next', x: 52, y: 52, priority: 2 },
      { id: 'edge', x: 99, y: 99, priority: 2 },
    ];
    const boxes = placeLabels(anchors, { w: 17, h: 7.5 });
    expect(boxes.find((b) => b.id === 'sel')).toBeTruthy();
    for (const b of boxes) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + b.w).toBeLessThanOrEqual(100);
      expect(b.y + b.h).toBeLessThanOrEqual(100);
    }
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++) {
        const p = boxes[i];
        const q = boxes[j];
        expect(p.x < q.x + q.w && p.x + p.w > q.x && p.y < q.y + q.h && p.y + p.h > q.y).toBe(false);
      }
  });
});

describe('badgeText', () => {
  it('says how late the vessel is and how far its ETA moved, as two facts', () => {
    expect(badgeText({ overdue: true, days_overdue: 2, slip_days: 14 })).toBe('2 days overdue · ETA moved +14 days');
    expect(badgeText({ overdue: true, days_overdue: 1, slip_days: 1 })).toBe('1 day overdue · ETA moved +1 day');
    expect(badgeText({ overdue: true, days_overdue: 8, slip_days: 0 })).toBe('8 days overdue');
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 7 })).toBe('ETA moved +7 days');
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 0 })).toBe('ETA unchanged');
  });

  it('a pulled-in ETA is not "unchanged" (GOV-008 minor)', () => {
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 0, eta_shift_days: -3 })).toBe('ETA pulled in 3 days');
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 0, eta_shift_days: -1 })).toBe('ETA pulled in 1 day');
    expect(badgeText({ overdue: true, days_overdue: 2, slip_days: 0, eta_shift_days: -5 })).toBe('2 days overdue · ETA pulled in 5 days');
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 0, eta_shift_days: 0 })).toBe('ETA unchanged');
    // The signed field wins over the clamped one; without it the old payload still reads as before.
    expect(badgeText({ overdue: false, days_overdue: 0, slip_days: 7, eta_shift_days: 7 })).toBe('ETA moved +7 days');
  });

  it('the history text does not claim "every report" when the ETA moved earlier', () => {
    const pulled = vessel({
      slip_days: 0,
      eta_shift_days: -4,
      history: { first_eta: '2026-11-09', first_report: '2026-09-29', current_eta: '2026-11-05', latest_report: '2026-10-27' },
    });
    expect(historyText(pulled)).toBe('9 Nov on 29 Sep → 5 Nov on 27 Oct');
    const same = vessel({ history: { first_eta: '2026-11-05', first_report: '2026-09-29', current_eta: '2026-11-05', latest_report: '2026-10-27' } });
    expect(historyText(same)).toBe('5 Nov in every report since 29 Sep');
  });
});

describe('portsInUse', () => {
  const ports = ['SHANGHAI', 'SHENZHEN', 'CHONGQING', 'SINGAPORE', 'ROTTERDAM', 'PORT LOUIS', 'CITY DEEP', 'DURBAN'].map((l) => ({ id: l, label: l }));

  it('is Durban alone with no vessels', () => {
    expect([...portsInUse([], ports)]).toEqual(['DURBAN']);
  });

  it('adds the origins and stops of each lane label and the discharge port, and nothing the lane merely passes', () => {
    const used = portsInUse(
      [
        vessel({ lane_label: 'Chongqing / Shenzhen → Durban → City Deep', deliver_port: 'ZAJNB' }),
        vessel({ id: 'v2', lane_label: 'Rotterdam → Durban', deliver_port: 'MUPLU' }),
      ],
      ports,
    );
    expect([...used].sort()).toEqual(['CHONGQING', 'CITY DEEP', 'DURBAN', 'PORT LOUIS', 'ROTTERDAM', 'SHENZHEN']);
    expect(used.has('SINGAPORE')).toBe(false);
    expect(used.has('SHANGHAI')).toBe(false);
  });

  it('ignores an origin that is not a port on the map ("China", "Origin not on the report")', () => {
    const used = portsInUse([vessel({ lane_label: 'China → Durban', deliver_port: 'ZADUR' }), vessel({ id: 'v2', lane_label: 'Origin not on the report → Durban', deliver_port: 'ZADUR' })], ports);
    expect([...used]).toEqual(['DURBAN']);
  });
});

describe('page scope into the map', () => {
  const base: ShippingFilterParams = {
    lineState: '', cargoStatus: '', distributorId: 7, customerId: null, purchaseOrderId: null, search: '', dateField: 'eta_date', dateFrom: '', dateTo: '', productFamily: '',
    productModel: '', currencyCode: '', operatingUnit: '', podDateFilter: '', planQuarter: '', planBusinessUnit: '', lineupAttribution: '', lifecycleBucket: '', slipDirection: '', cohort: '',
  };

  const SCOPE = '/api/v1/shipping/on-the-water?distributor_id=7';

  it('keeps who the page is about and nothing that picks lines for the grid', () => {
    expect(buildOnTheWaterUrl(base)).toBe(SCOPE);
    expect(buildOnTheWaterUrl({ ...base, vessel: 'i:2026-09-19|2026-11-05|ZAJNB|asia_durban' })).toBe(SCOPE);
    expect(buildOnTheWaterUrl({ ...base, cohort: 'needs_look' })).toBe(SCOPE);
    expect(buildOnTheWaterUrl({ ...base, cohort: 'overdue' })).toBe(SCOPE);
    expect(
      buildOnTheWaterUrl({
        ...base, lineState: 'shipped', cargoStatus: 'scheduled', search: 'x', dateField: 'effective_arrival_date', dateFrom: '2026-11-01', dateTo: '2026-11-08',
        podDateFilter: 'true', lifecycleBucket: 'shipped', slipDirection: 'slipped_out',
      }),
    ).toBe(SCOPE);
    expect(buildOnTheWaterUrl({ ...base, customerId: 3, purchaseOrderId: 9, productFamily: 'P', currencyCode: 'USD', planQuarter: '26Q4' })).toBe(
      '/api/v1/shipping/on-the-water?distributor_id=7&customer_id=3&purchase_order_id=9&product_family=P&currency_code=USD&plan_quarter=26Q4',
    );
  });
});

describe('label placement (GOV-008 batch 3)', () => {
  it('a wide label that fits no corner is tried one box higher before it is dropped', () => {
    // The anchor is near the left edge (no room to its left) and a port name blocks both right-hand corners.
    const anchor = { id: 'c:durban', x: 10, y: 50, priority: 1 };
    const size = { w: 30, h: 8 };
    const avoid = [{ id: 'p:CITY DEEP', x: 12, y: 38, w: 38, h: 24 }];
    const placed = placeLabels([anchor], size, avoid, { x: 2, y: 2 });
    expect(placed).toHaveLength(1); // before: 0, the label was dropped
    expect(placed[0].y).toBeLessThan(38 - size.h + 0.001);
    expect(placed[0].x).toBeGreaterThanOrEqual(0);
  });

  it('still takes the first free corner when there is one', () => {
    const placed = placeLabels([{ id: 'a', x: 50, y: 50, priority: 1 }], { w: 20, h: 8 }, [], { x: 2, y: 2 });
    expect(placed[0]).toMatchObject({ x: 52, y: 40 }); // right, above
  });
});

describe('label width (GOV-008 batch 3)', () => {
  it('is as wide as the label draws: the render of "4 vessels at or near Durban" was 201 px, the old reserved box 160 px', () => {
    expect(labelWidthPx('4 vessels at or near Durban', '3,494 u · ETA at port 31 Oct–5 Nov')).toBeGreaterThanOrEqual(201);
    expect(labelWidthPx('WWP · 25 u', '2 days overdue')).toBeLessThan(labelWidthPx('4 vessels at or near Durban', '3,494 u · ETA at port 31 Oct–5 Nov'));
  });

  it("placeLabels uses each anchor's own size, so a wide label is moved clear of a box a narrow one would fit beside", () => {
    const avoid = [{ id: 'p:CITY DEEP', x: 50, y: 40, w: 15, h: 3 }];
    const gap = { x: 2, y: 2 };
    const anchor = { id: 'c:durban', x: 30, y: 45, priority: 1 };
    const narrowBox = placeLabels([{ ...anchor, size: { w: 12, h: 6 } }], { w: 12, h: 6 }, avoid, gap)[0];
    const wideBox = placeLabels([{ ...anchor, size: { w: 30, h: 6 } }], { w: 12, h: 6 }, avoid, gap)[0];
    expect(narrowBox.w).toBe(12);
    expect(wideBox.w).toBe(30); // the box it was given, not the common size
    const hits = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    expect(hits(wideBox, avoid[0])).toBe(false);
  });
});
